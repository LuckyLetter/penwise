"""Spot changes that touch things an editor should never change on their own.

Numbers, citations, acronyms, math, code and links carry meaning the model
can't check. A change that removes or alters one is still shown, but it is not
applied unless you choose to apply it.
"""

from __future__ import annotations

import re

from penwise.i18n import N_, tr

# (what it is, pattern). The first kind found in the original wording wins.
PROTECTED = [
    (
        N_("a citation"),
        re.compile(
            r"\[\d+(?:\s*[,–-]\s*\d+)*\]"  # [3], [3, 5]
            # (Smith, 2020), (Smith et al. 2020; Lee 2021)
            r"|\([A-Z][\w'’-]+(?: et al\.| (?:and|&) [A-Z][\w'’-]+)?,? (?:19|20)\d\d[a-z]?(?:[;,] [^()]*)?\)"
            r"|\b[A-Z][\w'’-]+ et al\. \((?:19|20)\d\d[a-z]?\)"  # Smith et al. (2020)
        ),
    ),
    (N_("math"), re.compile(r"\$[^$]+\$")),
    # Without the punctuation after it: "see https://example.org, then…"
    (N_("a link"), re.compile(r"https?://\S*[^\s.,;:!?)\]'\"’”]|\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+")),
    # C:\Data\raw, /Users/ann/data/train.csv, ~/notes/ (not and/or, km/h or 1/2)
    (
        N_("a file path"),
        re.compile(r"\b[A-Za-z]:\\\S*[^\s.,;:!?)]|(?<![\w/])(?:~|\.{1,2})?/(?:[\w.@-]+/)+(?:[\w.@-]*[\w@-])?"),
    ),
    # \ref{fig:arch}, \cite[p. 3]{smith}, \textbf{x}
    (N_("LaTeX"), re.compile(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?(?:\{[^{}]*\})*")),
    # `x`, load(), get_data, --max-tokens
    (N_("code"), re.compile(r"`[^`]+`|\b[A-Za-z_]\w*\(\)|\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b|(?<![\w-])--?[a-z][\w-]*")),
    # A comma only in thousands: 1,000 is one number, [1,2] two.
    (N_("a number"), re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?%?|\d+(?:\.\d+)*%?")),
    (N_("an acronym"), re.compile(r"\b[A-Z][A-Z0-9]+s?\b")),
]

SPACE_FREE = {"a citation", "math"}


def risk(before: str, after: str, keep: list[str] | tuple[str, ...] = ()) -> str | None:
    """Return what a change would alter ("a number", ...), in the language of the settings, or None
    if it is safe to apply.

    `keep` lists words you never want changed (see `penwise keep`).
    """
    for word in keep:
        pattern = re.compile(rf"(?<!\w){re.escape(word)}(?!\w)")
        if len(pattern.findall(after)) < len(pattern.findall(before)):
            return tr("“{word}”, a word you keep", word=word)
    for kind, pattern in PROTECTED:
        # Spaces in a citation or a formula don't change it: [1,2] is [1, 2].
        same = (lambda item: re.sub(r"\s+", "", item)) if kind in SPACE_FREE else (lambda item: item)
        kept = [same(item) for item in pattern.findall(after)]
        for item in pattern.findall(before):
            if same(item) in kept:
                kept.remove(same(item))
            else:
                return tr(kind)
    return None


def risk_in(text: str, start: int, end: int, after: str, keep: list[str] | tuple[str, ...] = ()) -> str | None:
    """`risk` for replacing text[start:end] with `after`, judged on whole links, code and citations.

    A change to part of one (a_b → a-b in a web address) alters the whole of it, though the
    change alone doesn't look like a link.
    """
    low, high = start, end
    for _, pattern in PROTECTED:
        for match in pattern.finditer(text):
            first, last = match.span()
            inside = first < end and start < last if end > start else first < start < last
            if inside:
                low, high = min(low, first), max(high, last)
    return risk(text[low:high], text[low:start] + after + text[end:high], keep)
