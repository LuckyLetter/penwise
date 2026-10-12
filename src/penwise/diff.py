"""Word-level diff between your text and the model's edit.

The model only returns an edited text. Everything shown to you as a "change"
is computed here, deterministically, so what you see is exactly what differs.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import asdict, dataclass

# Words (keeping apostrophes inside them: don't, model's), whitespace runs,
# and single punctuation characters. Joining the tokens gives back the text.
_TOKEN = re.compile(r"\w+(?:['’]\w+)*|\s+|[^\w\s]")
WORD = re.compile(r"\w+(?:['’]\w+)*")

CONTEXT_CHARS = 40


@dataclass
class Change:
    id: int
    before: str
    after: str
    category: str = ""
    label: str = ""
    note: str = ""
    reason: str | None = None
    context_before: str = ""
    context_after: str = ""
    seen: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text)


def word_count(text: str) -> int:
    return len(WORD.findall(text))


def diff(original: str, edited: str, first_id: int = 0) -> tuple[list, list[Change]]:
    """Return (segments, changes) describing how to go from original to edited.

    A segment is either unchanged text (str) or the id of a Change (int).
    """
    a, b = tokenize(original), tokenize(edited)
    matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)

    blocks: list[list] = []  # [kind, before, after], kind is "same" or "change"
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        kind = "same" if tag == "equal" else "change"
        before, after = "".join(a[i1:i2]), "".join(b[j1:j2])
        if blocks and blocks[-1][0] == kind:
            blocks[-1][1] += before
            blocks[-1][2] += after
        else:
            blocks.append([kind, before, after])

    blocks = _keep_line_breaks(blocks)
    blocks = _bridge_rephrasings(blocks)

    segments: list = []
    changes: list[Change] = []
    pos = 0  # position in the original text
    for kind, before, after in blocks:
        if kind == "same":
            if segments and isinstance(segments[-1], str):
                segments[-1] += before
            else:
                segments.append(before)
        else:
            change = Change(
                id=first_id + len(changes),
                before=before,
                after=after,
                context_before=_context_before(original, pos),
                context_after=_context_after(original, pos + len(before)),
            )
            changes.append(change)
            segments.append(change.id)
        pos += len(before)
    return segments, changes


def apply(segments: list, changes: list[Change], accepted: set[int] | None = None) -> str:
    """Rebuild the text, using the edit for accepted changes (all by default)."""
    by_id = {c.id: c for c in changes}
    out = []
    for seg in segments:
        if isinstance(seg, str):
            out.append(seg)
        else:
            change = by_id[seg]
            out.append(change.after if accepted is None or seg in accepted else change.before)
    return "".join(out)


def similarity(original: str, edited: str) -> float:
    """How much of the original's wording survives in the edit (0..1)."""
    a = [w.lower() for w in WORD.findall(original)]
    b = [w.lower() for w in WORD.findall(edited)]
    if len(a) < 6:
        return difflib.SequenceMatcher(None, original.lower(), edited.lower(), autojunk=False).ratio()
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def _keep_line_breaks(blocks: list[list]) -> list[list]:
    """Never let the model move line breaks: they are your formatting, not an error."""
    out = []
    for kind, before, after in blocks:
        if kind == "change" and not before.strip() and not after.strip() and ("\n" in before or "\n" in after):
            kind, after = "same", before
        if out and out[-1][0] == kind == "same":
            out[-1][1] += before
            out[-1][2] += after
        else:
            out.append([kind, before, after])
    return out


def _bridge_rephrasings(blocks: list[list]) -> list[list]:
    """Join the pieces of one reworded phrase into a single change.

    Two changes are joined when only a space separates them and one of them is
    a rewrite, or when at most one word separates two rewrites. Small fixes
    next to each other (two typos, an article plus a verb form) stay separate,
    because each one is its own lesson.
    """

    def is_rewrite(block: list) -> bool:
        return max(word_count(block[1]), word_count(block[2])) >= 2

    def should_join(gap: str, left: list, right: list) -> bool:
        if "\n" in gap:
            return False
        if not gap.strip():
            return is_rewrite(left) or is_rewrite(right)
        return word_count(gap) <= 1 and is_rewrite(left) and is_rewrite(right)

    out: list[list] = []
    i = 0
    while i < len(blocks):
        block = blocks[i]
        if (
            block[0] == "same"
            and out
            and out[-1][0] == "change"
            and i + 1 < len(blocks)
            and blocks[i + 1][0] == "change"
            and should_join(block[1], out[-1], blocks[i + 1])
        ):
            nxt = blocks[i + 1]
            out[-1][1] += block[1] + nxt[1]
            out[-1][2] += block[2] + nxt[2]
            i += 2
            continue
        out.append(list(block))
        i += 1
    return out


def _context_before(text: str, pos: int) -> str:
    start = max(0, pos - CONTEXT_CHARS)
    snippet = text[start:pos].split("\n")[-1]
    if start > 0 and " " in snippet:
        snippet = snippet[snippet.index(" ") + 1 :]
    return snippet


def _context_after(text: str, pos: int) -> str:
    end = min(len(text), pos + CONTEXT_CHARS)
    snippet = text[pos:end].split("\n")[0]
    if end < len(text) and " " in snippet:
        snippet = snippet[: snippet.rindex(" ")]
    return snippet
