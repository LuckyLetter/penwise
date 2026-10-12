"""Spot changes that touch things an editor should never change on their own.

Numbers, citations, acronyms, math, code and links carry meaning the model
can't check. A change that removes or alters one is still shown, but it is not
applied unless you choose to apply it.
"""

from __future__ import annotations

import re

# (what it is, pattern). The first kind found in the original wording wins.
PROTECTED = [
    ("a citation", re.compile(r"\[\d+(?:\s*[,–-]\s*\d+)*\]")),
    ("math", re.compile(r"\$[^$]+\$|\\[a-zA-Z]+")),
    ("code", re.compile(r"`[^`]+`")),
    ("a link", re.compile(r"https?://\S+|\b[\w.+-]+@[\w-]+\.[\w.]+")),
    ("a number", re.compile(r"\d+(?:[.,]\d+)*%?")),
    ("an acronym", re.compile(r"\b[A-Z][A-Z0-9]+s?\b")),
]


def risk(before: str, after: str) -> str | None:
    """Return what a change would alter ("a number", ...), or None if it is safe to apply."""
    for kind, pattern in PROTECTED:
        kept = pattern.findall(after)
        for item in pattern.findall(before):
            if item in kept:
                kept.remove(item)
            else:
                return kind
    return None
