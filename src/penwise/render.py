"""Terminal output for `penwise check`."""

from __future__ import annotations

import os
import sys
from typing import TextIO

from penwise.engine import Result
from penwise.prompts import describe_change

RESET, BOLD, DIM, STRIKE = "\033[0m", "\033[1m", "\033[2m", "\033[9m"
RED, GREEN, YELLOW, CYAN = "\033[31m", "\033[32m", "\033[33m", "\033[36m"


def use_color(stream: TextIO) -> bool:
    return stream.isatty() and not os.environ.get("NO_COLOR")


def pretty(result: Result, color: bool) -> str:
    def paint(text: str, *styles: str) -> str:
        return "".join(styles) + text + RESET if color and text else text

    by_id = {c.id: c for c in result.changes}
    inline = []
    for seg in result.segments:
        if isinstance(seg, str):
            inline.append(seg)
            continue
        change = by_id[seg]
        if color:
            # Not every terminal shows strikethrough, so a replacement also gets an arrow.
            arrow = paint("→", DIM) if change.before.strip() and change.after.strip() else ""
            inline.append(paint(change.before, RED, STRIKE) + arrow + paint(change.after, GREEN))
        else:
            inline.append(
                (f"[-{change.before}-]" if change.before else "") + (f"{{+{change.after}+}}" if change.after else "")
            )

    count = len(result.changes)
    header = f"penwise · {result.mode} · {result.model} · {result.elapsed_ms / 1000:.1f}s"
    lines = [paint(header, DIM), "", "".join(inline).strip(), ""]

    for warning in result.warnings:
        lines += [paint(f"! {warning}", YELLOW), ""]

    if count == 0 and not result.warnings:
        lines.append(paint("No changes: your text looks good.", GREEN))
        return "\n".join(lines)

    lines.append(paint(f"{count} change{'s' if count != 1 else ''}", BOLD))
    for n, change in enumerate(result.changes, 1):
        seen = f"  (you've made this fix {change.seen}× before)" if change.seen else ""
        lines.append(
            f"{n:>3}. {describe_change(change.before, change.after)}  {paint(change.label, CYAN)}{paint(seen, DIM)}"
        )
        lines.append(paint(f"     {change.note}", DIM))
        if change.reason:
            lines.append(f"     Why: {change.reason}")
    return "\n".join(lines)


def write_pretty(result: Result, stream: TextIO | None = None) -> None:
    stream = stream or sys.stdout
    stream.write(pretty(result, use_color(stream)) + "\n")
