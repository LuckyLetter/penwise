"""A small local log of the changes you accepted, used to show your recurring patterns.

It stores only the changed words and a few words around them, never whole
texts, in a plain JSON Lines file you can read, edit, or delete.
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from penwise import lessons
from penwise.diff import Change


def history_path() -> Path:
    if os.environ.get("PENWISE_HISTORY"):
        return Path(os.environ["PENWISE_HISTORY"]).expanduser()
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(Path.home(), ".local", "share")
    return Path(base) / "penwise" / "history.jsonl"


def pair_key(before: str, after: str) -> str:
    def norm(s: str) -> str:
        return re.sub(r"\s+", " ", s.strip().lower().replace("’", "'"))

    return f"{norm(before)} → {norm(after)}"


def record(changes: list[dict], path: Path | None = None) -> int:
    """Append accepted changes. Returns how many were written."""
    path = path or history_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lines = []
    for c in changes:
        before, after = str(c.get("before", "")), str(c.get("after", ""))
        if before == after:
            continue
        lines.append(
            json.dumps(
                {
                    "time": now,
                    "before": before.strip(),
                    "after": after.strip(),
                    "category": c.get("category", ""),
                    "context": f"{c.get('context_before', '')}[{before.strip()}]{c.get('context_after', '')}"[:160],
                },
                ensure_ascii=False,
            )
        )
    if lines:
        with path.open("a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    return len(lines)


def load(path: Path | None = None) -> list[dict]:
    """The fixes you accepted. Lines that can't be read (cut off by a crash, say) are skipped:
    every check reads this file, so one bad line must never stop it."""
    path = path or history_path()
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:  # not there yet, or not readable
        return []
    entries = []
    for line in text.splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        fields = ("before", "after", "context")
        if isinstance(entry, dict) and all(isinstance(entry.get(field, ""), str) for field in fields):
            entries.append(entry)
    return entries


def mark_seen(changes: list[Change], path: Path | None = None) -> None:
    """Set change.seen to how many times you accepted the same fix before."""
    counts = Counter(pair_key(e.get("before", ""), e.get("after", "")) for e in load(path))
    for change in changes:
        change.seen = counts.get(pair_key(change.before, change.after), 0)


# Not mistakes, so not in your patterns: rewordings (Improve) and phrases Penwise wrote for you.
NOT_MISTAKES = {"rephrased", "filled"}


def around(entry: dict) -> tuple[str, str] | None:
    """The words just before and after the fix, as recorded; None when they can't be told apart."""
    before, found, after = entry.get("context", "").partition(f"[{entry.get('before', '')}]")
    return (before, after) if found else None


def lesson(entry: dict) -> tuple[str, str, str]:
    """The (kind, title, note) of a fix you accepted, worked out again from the fix and the words around it."""
    words_around = around(entry) or ("", "")
    category, note = lessons.classify(entry.get("before", ""), entry.get("after", ""), *words_around)
    return category, lessons.label(category, note), note


def example(entry: dict) -> dict | None:
    """A fix in the words around it, for the panel to show as you'd see it in your text."""
    words_around = around(entry)
    if words_around is None:
        return None
    return {
        "before_text": words_around[0],
        "before": entry.get("before", ""),
        "after": entry.get("after", ""),
        "after_text": words_around[1],
    }


def insights(path: Path | None = None, limit: int = 8) -> dict:
    """What you fix most (its rule, how often, your newest fix of the kind) and the fixes you keep
    making. Only mistakes count: not rewordings, nor phrases Penwise filled in for you."""
    mistakes = []
    for entry in load(path):
        kind, title, note = lesson(entry)
        if kind not in NOT_MISTAKES:
            mistakes.append((entry, (title, note), pair_key(entry.get("before", ""), entry.get("after", ""))))
    by_lesson = Counter(point for _, point, _ in mistakes)
    pairs = Counter(pair for _, _, pair in mistakes)
    newest_of_lesson = {point: entry for entry, point, _ in mistakes}  # later lines win
    newest_of_pair = {pair: entry for entry, _, pair in mistakes}
    return {
        "total": len(mistakes),
        "first": mistakes[0][0].get("time") if mistakes else None,
        "lessons": [
            (title, note, n, newest_of_lesson[title, note]) for (title, note), n in by_lesson.most_common(limit)
        ],
        "repeated": [(pair, n, newest_of_pair[pair]) for pair, n in pairs.most_common(limit) if n > 1],
    }


def clear(path: Path | None = None) -> bool:
    path = path or history_path()
    if path.exists():
        path.unlink()
        return True
    return False
