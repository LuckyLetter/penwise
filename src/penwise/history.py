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
    path = path or history_path()
    if not path.exists():
        return []
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def mark_seen(changes: list[Change], path: Path | None = None) -> None:
    """Set change.seen to how many times you accepted the same fix before."""
    counts = Counter(pair_key(e.get("before", ""), e.get("after", "")) for e in load(path))
    for change in changes:
        change.seen = counts.get(pair_key(change.before, change.after), 0)


def insights(path: Path | None = None, limit: int = 8) -> dict:
    entries = load(path)
    categories = Counter(e.get("category") or "other" for e in entries)
    pairs = Counter(pair_key(e.get("before", ""), e.get("after", "")) for e in entries)
    examples: dict[str, str] = {}
    for e in reversed(entries):  # newest example wins
        examples.setdefault(pair_key(e.get("before", ""), e.get("after", "")), e.get("context", ""))
    return {
        "total": len(entries),
        "first": entries[0].get("time") if entries else None,
        "categories": categories.most_common(limit),
        "repeated": [(k, n, examples.get(k, "")) for k, n in pairs.most_common(limit) if n > 1],
    }


def clear(path: Path | None = None) -> bool:
    path = path or history_path()
    if path.exists():
        path.unlink()
        return True
    return False
