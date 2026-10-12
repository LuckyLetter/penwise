"""The check pipeline: split → ask the model → clean → sanity-check → diff → explain."""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from penwise import diff as textdiff
from penwise import lessons, prompts
from penwise.diff import Change
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
        return textdiff.apply(self.segments, self.changes)

    def to_dict(self) -> dict:
        return {
            "type": "result",
            "mode": self.mode,
            "model": self.model,
            "original": self.original,
            "edited": self.edited,
            "segments": [{"text": s} if isinstance(s, str) else {"change": s} for s in self.segments],
            "changes": [c.to_dict() for c in self.changes],
            "warnings": self.warnings,
            "elapsed_ms": self.elapsed_ms,
        }


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
        return "the model returned nothing"
    if _REPLY.match(edited) and not _REPLY.match(original):
        return "the model replied to your text instead of editing it"
    # Text being filled in is partly translated, so it may grow a lot and share fewer words.
    if len(edited) > (4 * len(original) + 80 if fill else 2 * len(original) + 40):
        return "the model's answer was much longer than your text"
    if len(edited) < 0.3 * len(original) and not fill:
        return "the model's answer was much shorter than your text"
    if not fill and textdiff.similarity(original, edited) < MIN_SIMILARITY[mode]:
        return "the model's answer didn't look like an edit of your text"
    return None


Chat = Callable[[str, list[dict]], str]
Emit = Callable[[dict], None]


def check(
    text: str,
    chat: Chat,
    mode: str = "fix",
    model: str = "",
    explain: bool = False,
    max_chunk_chars: int = 1200,
    on_event: Emit | None = None,
    annotate_seen: Callable[[list[Change]], None] | None = None,
) -> Result:
    """Check `text` and return the result. `chat(system, messages)` calls the model."""
    emit = on_event or (lambda event: None)
    started = time.monotonic()
    result = Result(original=text, mode=mode, model=model)
    edited_chunks: list[tuple[str, str, list[Change]]] = []  # (original, edited, changes) per chunk

    pieces = split(text, max_chunk_chars)
    edits = iter(_parallel([lambda p=piece: _edit(chat, p, mode) for piece, editable in pieces if editable]))
    for piece, editable in pieces:
        if not editable:
            _append(result.segments, piece)
            continue
        edited, problem = next(edits)
        if problem:
            result.warnings.append(
                f"Part of your text was left as is because {problem}. "
                "Try again, try the other mode, or use a larger model."
            )
        segments, changes = textdiff.diff(piece, edited, first_id=len(result.changes))
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


def _edit(chat: Chat, piece: str, mode: str) -> tuple[str, str | None]:
    """Ask the model to edit one piece. Returns (edited text, why it was rejected or None)."""
    fill = needs_fill(piece)
    system, messages = prompts.edit_messages(piece, mode, fill=fill)
    edited = clean(chat(system, messages), piece)
    problem = sanity_check(piece, edited, mode, fill=fill)
    return (piece, problem) if problem else (edited, None)


def _parallel(calls: list[Callable]) -> list:
    """Run the calls at the same time and return their results in order."""
    if len(calls) <= 1:
        return [call() for call in calls]
    with ThreadPoolExecutor(max_workers=PARALLEL_REQUESTS) as pool:
        return list(pool.map(lambda call: call(), calls))


def explain_changes(chat: Chat, original: str, edited: str, changes: list[Change]) -> dict[int, str]:
    system, messages = prompts.explain_messages(original, edited, [(c.before, c.after) for c in changes])
    try:
        raw = chat(system, messages)
    except LLMError:  # explanations are a bonus; never lose the edit because of them
        return {}
    return parse_reasons(raw, [c.id for c in changes])


def parse_reasons(raw: str, ids: list[int]) -> dict[int, str]:
    reasons: dict[int, str] = {}
    for line in _THINK.sub("", raw).splitlines():
        m = re.match(r"^\s*(?:[-*]\s*)?(\d+)\s*[.):]\s*(.+?)\s*$", line)
        if not m:
            continue
        n = int(m.group(1))
        reason = m.group(2).replace("**", "").strip()
        if 1 <= n <= len(ids) and ids[n - 1] not in reasons and reason:
            reasons[ids[n - 1]] = reason[:200]
    return reasons


def _append(segments: list, seg) -> None:
    if isinstance(seg, str) and segments and isinstance(segments[-1], str):
        segments[-1] += seg
    else:
        segments.append(seg)
