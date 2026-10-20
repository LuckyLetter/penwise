"""The check pipeline: split → ask the model → clean → sanity-check → diff → explain."""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from penwise import diff as textdiff
from penwise import i18n, lessons, prompts, protect
from penwise.diff import Change
from penwise.i18n import N_, tr
from penwise.llm import LLMError

# Below this word-level similarity, an "edit" is most likely the model answering
# or rewriting the text instead of editing it, and is not offered to you.
MIN_SIMILARITY = {"fix": 0.5, "improve": 0.25}
EXPLAIN_BATCH = 8
# Paragraphs are sent to the model at the same time, up to this many at once.
PARALLEL_REQUESTS = 4

_PARAGRAPH_BREAK = re.compile(r"\n[ \t]*\n\s*")
_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+(?=[\"“(\[]?[A-Z0-9])")
_PREAMBLE = re.compile(
    r"^\s*(?:sure|certainly|of course|okay|ok|here(?:'s| is| are)|the (?:corrected|edited|revised|improved)"
    r"|corrected|edited|revised|improved)\b[^\n]*:\s*\n",
    re.IGNORECASE,
)
_LABEL = re.compile(
    r"^\s*(?:(?:corrected|edited|revised|improved)(?: text| version)?|(?:correct|improve) this text"
    r"|write this in english)\s*:\s*",
    re.IGNORECASE,
)
_TRAILING_NOTE = re.compile(
    r"\n\s*\n\s*(?:\*\*)?(?:note|notes|changes|explanation|explanations)\b.*$", re.IGNORECASE | re.DOTALL
)
_REPLY = re.compile(
    r"^\s*(?:here(?:'s| is| are)|sure\b|certainly\b|of course\b|i'd\b|i would\b|i can\b|i'm sorry|as an ai)",
    re.IGNORECASE,
)
_THINK = re.compile(r"<think>.*?</think>\s*|^.*?</think>\s*", re.DOTALL)
_END_PUNCTUATION = re.compile(r"[.,;:!?]+$")
_LIST_ITEM = re.compile(r"[ \t]*(?:[-*•]|\d+[.)])[ \t]+")
_QUOTES = [("```", "```"), ('"""', '"""'), ('"', '"'), ("“", "”"), ("'", "'"), ("‘", "’")]


@dataclass
class Result:
    original: str
    mode: str
    model: str
    segments: list = field(default_factory=list)
    changes: list[Change] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    elapsed_ms: int = 0

    @property
    def edited(self) -> str:
        """The text with every change applied, except the ones that would alter a number, citation, etc."""
        return textdiff.apply(self.segments, self.changes, {c.id for c in self.changes if not c.risk})

    def to_dict(self) -> dict:
        return {
            "type": "result",
            "mode": self.mode,
            "model": self.model,
            "original": self.original,
            "edited": self.edited,
            "segments": [{"text": s} if isinstance(s, str) else {"change": s} for s in self.segments],
            "changes": [_shown(c) for c in self.changes],
            "warnings": self.warnings,
            "elapsed_ms": self.elapsed_ms,
        }


def _shown(change: Change) -> dict:
    """A change as the panel shows it: its title and note in the language of the settings."""
    shown = change.to_dict()
    shown.update({key: tr(shown[key]) for key in ("label", "note") if shown.get(key)})
    return shown


def split(text: str, max_chars: int = 1200) -> list[tuple[str, bool]]:
    """Cut text into (piece, editable) parts that join back to the exact original.

    Paragraphs are sent to the model one at a time, which keeps small models
    focused and keeps your paragraph breaks untouched.
    """
    parts: list[tuple[str, bool]] = []

    def add(piece: str, editable: bool) -> None:
        if piece:
            parts.append((piece, editable))

    pos = 0
    for match in list(_PARAGRAPH_BREAK.finditer(text)) + [None]:
        end = match.start() if match else len(text)
        paragraph = text[pos:end]
        stripped = paragraph.strip()
        if stripped:
            lead = paragraph[: len(paragraph) - len(paragraph.lstrip())]
            trail = paragraph[len(paragraph.rstrip()) :]
            add(lead, False)
            for piece, editable in _split_long(stripped, max_chars):
                add(piece, editable)
            add(trail, False)
        else:
            add(paragraph, False)
        if match:
            add(match.group(0), False)
            pos = match.end()
    return parts


def _split_long(paragraph: str, max_chars: int) -> list[tuple[str, bool]]:
    if len(paragraph) <= max_chars:
        return [(paragraph, True)]
    parts: list[tuple[str, bool]] = []
    chunk_start = 0
    last_break: re.Match | None = None
    for brk in _SENTENCE_BREAK.finditer(paragraph):
        if brk.start() - chunk_start > max_chars and last_break is not None:
            parts.append((paragraph[chunk_start : last_break.start()], True))
            parts.append((last_break.group(0), False))
            chunk_start = last_break.end()
        last_break = brk
    if len(paragraph) - chunk_start > max_chars and last_break is not None and last_break.start() > chunk_start:
        parts.append((paragraph[chunk_start : last_break.start()], True))
        parts.append((last_break.group(0), False))
        chunk_start = last_break.end()
    parts.append((paragraph[chunk_start:], True))
    return parts


def clean(raw: str, original: str) -> str:
    """Strip the wrapping that small models like to add around their answer."""
    text = _THINK.sub("", raw).strip()
    text = _PREAMBLE.sub("", text, count=1).strip()
    if not _LABEL.match(original):
        text = _LABEL.sub("", text, count=1).strip()
    if not _TRAILING_NOTE.search(original):
        text = _TRAILING_NOTE.sub("", text).strip()
    # Markdown the model added for emphasis: **by**, *by* (never in your text, so never pasted there).
    if "**" not in original:
        text = re.sub(r"\*\*(\S(?:.*?\S)?)\*\*", r"\1", text)
    if "*" not in original:
        text = re.sub(r"(?<![\w*])\*(\S(?:[^*\n]*?\S)?)\*(?![\w*])", r"\1", text)
    for left, right in _QUOTES:
        if (
            text.startswith(left)
            and text.endswith(right)
            and len(text) > len(left) + len(right)
            and not original.startswith(left)
        ):
            text = text[len(left) : -len(right)].strip()
            if left == "```":
                text = re.sub(r"^[a-zA-Z]*\n", "", text)
    return _match_quote_style(text, original)


def _match_quote_style(text: str, original: str) -> str:
    """Don't report straight vs. curly quotes as changes when the writer didn't use curly ones."""
    if not re.search("[‘’“”]", original):
        text = text.replace("‘", "'").replace("’", "'").replace("“", '"').replace("”", '"')
    elif "'" not in original:
        text = text.replace("'", "’")
    return text


def needs_fill(text: str) -> bool:
    return bool(textdiff.NEEDS_FILL.search(text))


def sanity_check(original: str, edited: str, mode: str, fill: bool = False) -> str | None:
    """Return a reason to reject the edit, or None if it looks like an edit of the original."""
    if not edited.strip():
        return N_("the model returned nothing")
    if _REPLY.match(edited) and not _REPLY.match(original):
        return N_("the model replied to your text instead of editing it")
    # Text being filled in is partly translated, so it may grow a lot and share fewer words.
    if len(edited) > (4 * len(original) + 80 if fill else 2 * len(original) + 40):
        return N_("the model's answer was much longer than your text")
    if len(edited) < 0.3 * len(original) and not fill:
        return N_("the model's answer was much shorter than your text")
    if not fill and textdiff.similarity(original, edited) < MIN_SIMILARITY[mode]:
        return N_("the model's answer didn't look like an edit of your text")
    return None


Chat = Callable[[str, list[dict]], str]
Emit = Callable[[dict], None]


def _mark_risks(piece: str, segments: list, changes: list[Change], keep) -> None:
    """Hold back changes to numbers, links, code…: each judged where it is in `piece`."""
    by_id = {change.id: change for change in changes}
    pos = 0
    for seg in segments:
        if isinstance(seg, str):
            pos += len(seg)
            continue
        change = by_id[seg]
        change.risk = protect.risk_in(piece, pos, pos + len(change.before), change.after, keep)
        # A model that stops early drops the rest of your text: that is never applied on its own.
        dropped = not change.after.strip() and len(change.before.split()) >= 4 and re.search(r"[.!?]", change.before)
        if dropped and not change.risk:
            change.risk = tr("a whole sentence")
        # Your lines and lists are your layout: a list made into a sentence, or lines joined with
        # commas, is shown but not applied.
        at_line_start = pos == 0 or piece[pos - 1] == "\n"
        unlisted = at_line_start and _LIST_ITEM.match(change.before) and not _LIST_ITEM.match(change.after)
        if (change.before.count("\n") != change.after.count("\n") or unlisted) and not change.risk:
            change.risk = tr("the layout")
        pos += len(change.before)


def check(
    text: str,
    chat: Chat,
    mode: str = "fix",
    model: str = "",
    explain: bool = False,
    max_chunk_chars: int = 1200,
    on_event: Emit | None = None,
    annotate_seen: Callable[[list[Change]], None] | None = None,
    keep: list[str] | tuple[str, ...] = (),
    style: str = "",
) -> Result:
    """Check `text` and return the result. `chat(system, messages)` calls the model."""
    emit = on_event or (lambda event: None)
    started = time.monotonic()
    result = Result(original=text, mode=mode, model=model)
    edited_chunks: list[tuple[str, str, list[Change]]] = []  # (original, edited, changes) per chunk

    pieces = split(text, max_chunk_chars)
    edits = iter(_parallel([lambda p=piece: _edit(chat, p, mode, style) for piece, editable in pieces if editable]))
    for piece, editable in pieces:
        if not editable:
            _append(result.segments, piece)
            continue
        edited, problem = next(edits)
        if problem:
            result.warnings.append(
                tr(
                    "Part of your text was left as is because {problem}. "
                    "Try again, try the other mode, or use a larger model.",
                    problem=tr(problem),
                )
            )
        segments, changes = textdiff.diff(piece, edited, first_id=len(result.changes))
        segments, changes = _split_end_punctuation(segments, changes, first_id=len(result.changes))
        _mark_risks(piece, segments, changes, keep)
        for seg in segments:
            _append(result.segments, seg)
        result.changes.extend(changes)
        if changes:
            edited_chunks.append((piece, textdiff.apply(segments, changes), changes))

    lessons.annotate(result.changes)
    if annotate_seen:
        annotate_seen(result.changes)
    result.elapsed_ms = int((time.monotonic() - started) * 1000)
    emit(result.to_dict())

    if explain:
        batches = [
            (original_chunk, edited_chunk, changes[i : i + EXPLAIN_BATCH])
            for original_chunk, edited_chunk, changes in edited_chunks
            for i in range(0, len(changes), EXPLAIN_BATCH)
        ]
        with ThreadPoolExecutor(max_workers=PARALLEL_REQUESTS) as pool:
            futures = {pool.submit(explain_changes, chat, *batch): batch[2] for batch in batches}
            for future in as_completed(futures):  # show each batch of reasons as soon as it arrives
                reasons = future.result()
                if reasons:
                    for change in futures[future]:
                        change.reason = reasons.get(change.id, change.reason)
                    emit({"type": "explanations", "reasons": {str(k): v for k, v in reasons.items()}})
    return result


def _split_end_punctuation(segments: list, changes: list[Change], first_id: int) -> tuple[list, list[Change]]:
    """Give the punctuation added at the end of a change a change of its own.

    It is a fix by itself, with its own lesson: "sample" → "samples." is a word form and a
    period. And it is applied even where the rest is not: in "LLMs" → "large language models."
    the acronym stays unless you choose otherwise, but the period goes in. Changes are numbered
    again.
    """
    by_id = {c.id: c for c in changes}
    out_segments: list = []
    out_changes: list[Change] = []
    for seg in segments:
        if isinstance(seg, str):
            out_segments.append(seg)
            continue
        change = by_id[seg]
        mark = _END_PUNCTUATION.search(change.after)
        parts = [change]
        if mark and mark.start() > 0 and not change.before.endswith(mark.group()):
            contexts = {"context_before": change.context_before, "context_after": change.context_after}
            rest = change.after[: mark.start()]
            # "work" → "work." is just the period: the word stays plain text.
            if rest == change.before:
                parts = [change.before]
            else:
                parts = [Change(id=0, before=change.before, after=rest, **contexts)]
            parts.append(Change(id=0, before="", after=mark.group(), **contexts))
        for part in parts:
            if isinstance(part, str):
                out_segments.append(part)
                continue
            part.id = first_id + len(out_changes)
            out_changes.append(part)
            out_segments.append(part.id)
    return out_segments, out_changes


def _edit(chat: Chat, piece: str, mode: str, style: str = "") -> tuple[str, str | None]:
    """Ask the model to edit one piece. Returns (edited text, why it was rejected or None)."""
    # List numbers and bullets never go to the model: small models drop or redo them, and the
    # fixes on those lines would go with them. They are put back on the same lines after.
    markers, text = _take_list_markers(piece)
    fill = needs_fill(text)
    system, messages = prompts.edit_messages(text, mode, fill=fill, style=style)
    edited = clean(chat(system, messages), text)
    problem = sanity_check(text, edited, mode, fill=fill)
    if not problem and any(markers):
        edited = _put_list_markers(markers, edited)
        problem = None if edited is not None else N_("the model joined or split the lines of your list")
    return (piece, problem) if problem else (edited, None)


def _take_list_markers(piece: str) -> tuple[list[str], str]:
    """Each line's list number or bullet ("1. ", "- ", or ""), and the text without them."""
    markers, lines = [], []
    for line in piece.split("\n"):
        marker = _LIST_ITEM.match(line)
        markers.append(marker[0] if marker else "")
        lines.append(line[marker.end() :] if marker else line)
    return markers, "\n".join(lines)


def _put_list_markers(markers: list[str], edited: str) -> str | None:
    """The numbers and bullets back on their lines; None when the lines don't match up any more."""
    lines = edited.split("\n")
    if len(lines) != len(markers):
        return None
    return "\n".join(
        marker + _LIST_ITEM.sub("", line, count=1).lstrip() if marker else line  # the model's own, if any, goes
        for marker, line in zip(markers, lines, strict=True)
    )


def _parallel(calls: list[Callable]) -> list:
    """Run the calls at the same time and return their results in order."""
    if len(calls) <= 1:
        return [call() for call in calls]
    with ThreadPoolExecutor(max_workers=PARALLEL_REQUESTS) as pool:
        return list(pool.map(lambda call: call(), calls))


def explain_changes(chat: Chat, original: str, edited: str, changes: list[Change]) -> dict[int, str]:
    pairs = [(c.before, c.after) for c in changes]
    system, messages = prompts.explain_messages(original, edited, pairs, language=i18n.language())
    try:
        raw = chat(system, messages)
    except LLMError:  # explanations are a bonus; never lose the edit because of them
        return {}
    return parse_reasons(raw, [c.id for c in changes])


_NUMBERED = re.compile(r"^\s*(?:[-*]\s*)?(?:change\s*)?(\d+)\s*[.):]\s*(.*?)\s*$", re.IGNORECASE)
_BULLET = re.compile(r"^\s*[-*•]\s+(.+?)\s*$")
# The model repeating the change before its reason: "have" → "has": …
_REPEATED_CHANGE = re.compile(r"^[\"“'‘].*?[\"”'’]\s*(?:→|->)\s*[\"“'‘].*?[\"”'’]\s*[:—–-]\s*")


def parse_reasons(raw: str, ids: list[int]) -> dict[int, str]:
    """The model's reason for each change, from its numbered list (as loosely as models write it)."""
    lines = _THINK.sub("", raw).replace("**", "").splitlines()
    found: list[tuple[int, str]] = []  # (number, reason), a reason that wraps joined up
    bullets: list[str] = []
    going_on = False  # whether the next line may still be part of the last reason
    for line in lines:
        numbered = _NUMBERED.match(line)
        bullet = _BULLET.match(line)
        if numbered:
            found.append((int(numbered[1]), numbered[2]))
        elif bullet:
            bullets.append(bullet[1])
        elif going_on and line.strip():
            found[-1] = (found[-1][0], f"{found[-1][1]} {line.strip()}")
        going_on = bool(found) and bool(line.strip()) and not bullet  # a blank line ends a reason
    if not found and len(bullets) == len(ids):  # no numbers, but one line for each change
        found = list(enumerate(bullets, 1))
    reasons: dict[int, str] = {}
    for n, text in found:
        reason = _REPEATED_CHANGE.sub("", text.strip()).strip()
        reason = reason[:1].upper() + reason[1:]
        if 1 <= n <= len(ids) and ids[n - 1] not in reasons and reason:
            reasons[ids[n - 1]] = reason[:200]
    return reasons


def _append(segments: list, seg) -> None:
    if isinstance(seg, str) and segments and isinstance(segments[-1], str):
        segments[-1] += seg
    else:
        segments.append(seg)
