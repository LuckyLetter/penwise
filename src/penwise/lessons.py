"""Label each change and attach a short, fixed teaching note.

These notes are written by people, not generated, so they are always the same
for the same kind of change. The model's own one-line "why" is shown separately.
"""

from __future__ import annotations

import os
import re

from penwise.diff import NEEDS_FILL, WORD, Change

ARTICLES = {"a", "an", "the"}

PREPOSITIONS = {
    "about",
    "above",
    "across",
    "after",
    "against",
    "along",
    "among",
    "around",
    "as",
    "at",
    "before",
    "behind",
    "below",
    "beneath",
    "beside",
    "besides",
    "between",
    "beyond",
    "by",
    "despite",
    "down",
    "during",
    "except",
    "for",
    "from",
    "in",
    "inside",
    "into",
    "like",
    "near",
    "of",
    "off",
    "on",
    "onto",
    "out",
    "outside",
    "over",
    "per",
    "since",
    "through",
    "throughout",
    "to",
    "toward",
    "towards",
    "under",
    "until",
    "upon",
    "via",
    "with",
    "within",
    "without",
}

# Groups of irregular forms of the same verb.
IRREGULAR = [
    {"be", "is", "are", "was", "were", "been", "being", "am"},
    {"have", "has", "had", "having"},
    {"do", "does", "did", "done", "doing"},
    {"go", "goes", "went", "gone", "going"},
    {"make", "makes", "made", "making"},
    {"take", "takes", "took", "taken", "taking"},
    {"give", "gives", "gave", "given", "giving"},
    {"write", "writes", "wrote", "written", "writing"},
    {"show", "shows", "showed", "shown", "showing"},
    {"find", "finds", "found", "finding"},
    {"see", "sees", "saw", "seen", "seeing"},
    {"choose", "chooses", "chose", "chosen", "choosing"},
    {"lead", "leads", "led", "leading"},
    {"this", "these"},
    {"that", "those"},
]

INFLECTION_ENDINGS = {"", "s", "es", "ed", "d", "ing", "y", "ies", "ied", "er", "est", "ly", "e"}

UNCOUNTABLE = {
    "advice",
    "equipment",
    "evidence",
    "feedback",
    "hardware",
    "homework",
    "information",
    "knowledge",
    "luggage",
    "progress",
    "research",
    "software",
    "furniture",
    "training",
}

# Commonly confused words. Either direction gets the same note.
CONFUSABLE = {
    frozenset({"its", "it's"}): "“its” means belonging to it (its accuracy); “it's” means it is or it has.",
    frozenset({"their", "there"}): "“their” = belonging to them; “there” = a place, or “there is/are”.",
    frozenset({"their", "they're"}): "“their” = belonging to them; “they're” = they are.",
    frozenset({"there", "they're"}): "“there” = a place, or “there is/are”; “they're” = they are.",
    frozenset({"then", "than"}): "“than” compares (better than); “then” is about time or order (and then).",
    frozenset(
        {"affect", "effect"}
    ): "Usually “affect” is the verb (noise affects accuracy) and “effect” the noun (the effect of noise).",
    frozenset(
        {"affects", "effects"}
    ): "Usually “affect” is the verb (noise affects accuracy) and “effect” the noun (the effects of noise).",
    frozenset({"whose", "who's"}): "“whose” = belonging to whom; “who's” = who is.",
    frozenset({"your", "you're"}): "“your” = belonging to you; “you're” = you are.",
    frozenset({"lose", "loose"}): "“lose” is the verb (lose data); “loose” means not tight.",
    frozenset(
        {"which", "that"}
    ): "“that” starts a clause that defines the noun (no commas); “which” adds extra information, usually after a comma.",
    frozenset({"less", "fewer"}): "“fewer” for things you can count (fewer samples); “less” for amounts (less noise).",
    frozenset(
        {"amount", "number"}
    ): "“number of” for countable nouns (number of users); “amount of” for uncountable ones (amount of data).",
    frozenset({"among", "between"}): "“between” for two things or clearly separate items; “among” for a group.",
    frozenset({"e g", "i e"}): "“e.g.” = for example (one of several); “i.e.” = that is (the exact thing).",
    frozenset({"principal", "principle"}): "“principle” = a rule or idea; “principal” = main (principal component).",
    frozenset({"discrete", "discreet"}): "“discrete” = separate, countable (discrete variables); “discreet” = tactful.",
    frozenset({"complement", "compliment"}): "“complement” = complete or go well with; “compliment” = praise.",
    frozenset({"accept", "except"}): "“accept” = agree to receive; “except” = apart from.",
    frozenset({"advice", "advise"}): "“advice” is the noun; “advise” is the verb.",
    frozenset({"lead", "led"}): "The past tense of “lead” is “led”.",
    frozenset({"loss", "lose"}): "“lose” is the verb; “loss” is the noun.",
    frozenset({"to", "too"}): "“too” = also, or more than enough; “to” is the preposition or infinitive marker.",
}

LABELS = {
    "spelling": "Spelling",
    "capitalization": "Capitalization",
    "punctuation": "Punctuation",
    "spacing": "Spacing",
    "article": "Articles",
    "preposition": "Prepositions",
    "word-form": "Word form",
    "uncountable": "Uncountable noun",
    "confusable": "Commonly confused",
    "word-choice": "Word choice",
    "added": "Missing word",
    "removed": "Extra words",
    "rephrased": "Rephrasing",
    "filled": "Filled in",
}

NOTES = {
    "spelling": "A misspelled word or a typo.",
    "capitalization": "Capitalize the first word of a sentence, names, and acronyms; keep ordinary words lowercase mid-sentence.",
    "punctuation": "Punctuation shows the reader how the sentence is built.",
    "spacing": "One space between words, and no space before , . ; : ? !",
    "article": "“the” points to something specific or already known; “a/an” introduces one of many; general plurals and uncountable nouns often take no article (Models fail when…, Research shows…).",
    "preposition": "Prepositions are mostly fixed by habit, so learn them in phrases: depend on, interested in, on the other hand, in this paper, at the end.",
    "word-form": "Same word, different form: singular/plural, tense, or agreement with the subject (the result shows, the results show).",
    "uncountable": "Some nouns are uncountable in English: no plural and no “a/an” (information, research, feedback, evidence). Count them with “pieces of” or “studies”.",
    "word-choice": "A more precise or more natural word for this context.",
    "confusable": "Pairs of words that are easy to mix up (then/than, its/it's, affect/effect). Check the pair each time.",
    "added": "A missing word was added so the sentence is complete and grammatical.",
    "removed": "Words that add no meaning were removed; shorter is usually clearer.",
    "rephrased": "Reworded to read more naturally in English.",
    "filled": "Your own words or [[note]], written in English for you. Learn this phrase for next time.",
}

A_AN_NOTE = "Use “an” before a vowel sound (an hour, an LLM, an MRI scan) and “a” before a consonant sound (a user, a one-off, a URL)."
COMMA_ADDED_NOTE = "A comma usually follows an opening word or phrase (However, In this work,) and goes before and/but/so when they join two full sentences."
SPLICE_NOTE = "A comma alone can't join two full sentences: use a semicolon or a full stop, or add and/but/so."
COMMA_REMOVED_NOTE = (
    "English uses fewer commas than many languages: none between a subject and its verb, or before a “that” clause."
)
HYPHEN_NOTE = (
    "Hyphenate words that together describe a noun that follows them (a well-known method, state-of-the-art results)."
)
APOSTROPHE_NOTE = "An apostrophe marks possession (the model's output) or a contraction (it's = it is)."
GAP_NOTE = "The word that fits your [[?]]. Words that go together (consistent with, express gratitude) are best learned as a pair."
GAP = re.compile(r"\[\[\s*\?*\s*\]\]")


def words(text: str) -> list[str]:
    return [w.lower().replace("’", "'") for w in WORD.findall(text)]


def classify(before: str, after: str) -> tuple[str, str]:
    """Return (category, note) for one change."""
    b, a = before.strip(), after.strip()
    bw, aw = words(b), words(a)

    if NEEDS_FILL.search(b):
        return "filled", GAP_NOTE if GAP.fullmatch(b) else NOTES["filled"]
    if b == a:
        return "spacing", NOTES["spacing"]
    if b.lower() == a.lower():
        return "capitalization", NOTES["capitalization"]
    if bw == aw:
        return "punctuation", _punctuation_note(b, a)

    key = frozenset({" ".join(bw), " ".join(aw)})
    if len(key) == 2 and key in CONFUSABLE:
        return "confusable", CONFUSABLE[key]

    if len(bw) == 1 and len(aw) == 1:
        x, y = bw[0], aw[0]
        if y in UNCOUNTABLE and x in (y + "s", y + "es"):
            return "uncountable", NOTES["uncountable"]
        if {x, y} == {"a", "an"}:
            return "article", A_AN_NOTE

    changed = set(bw) ^ set(aw) or set(bw) | set(aw)
    if changed and changed <= ARTICLES:
        return "article", NOTES["article"]
    if changed and changed <= PREPOSITIONS:
        return "preposition", NOTES["preposition"]

    if len(bw) == 1 and len(aw) == 1:
        x, y = bw[0], aw[0]
        if _same_word(x, y):
            return "word-form", NOTES["word-form"]
        if _edit_distance(x, y) <= (1 if min(len(x), len(y)) <= 4 else 2):
            return "spelling", NOTES["spelling"]
        return "word-choice", NOTES["word-choice"]

    if not bw and aw:
        return "added", NOTES["added"]
    if bw and not aw:
        return "removed", NOTES["removed"]
    if _is_subsequence(aw, bw):
        return "removed", NOTES["removed"]
    if _is_subsequence(bw, aw) and len(aw) - len(bw) == 1:
        return "added", NOTES["added"]
    return "rephrased", NOTES["rephrased"]


def annotate(changes: list[Change]) -> None:
    for change in changes:
        change.category, change.note = classify(change.before, change.after)
        change.label = LABELS[change.category]


def _punctuation_note(before: str, after: str) -> str:
    if after.count(",") > before.count(","):
        return COMMA_ADDED_NOTE
    if after.count(",") < before.count(","):
        joined = sum(after.count(mark) - before.count(mark) for mark in ";.") > 0
        return SPLICE_NOTE if joined else COMMA_REMOVED_NOTE
    if after.count("-") > before.count("-"):
        return HYPHEN_NOTE
    if after.count("'") + after.count("’") != before.count("'") + before.count("’"):
        return APOSTROPHE_NOTE
    return NOTES["punctuation"]


def _same_word(x: str, y: str) -> bool:
    if any(x in group and y in group for group in IRREGULAR):
        return True
    prefix = len(os.path.commonprefix([x, y]))
    return prefix >= 2 and x[prefix:] in INFLECTION_ENDINGS and y[prefix:] in INFLECTION_ENDINGS


def _edit_distance(x: str, y: str) -> int:
    """Damerau-Levenshtein distance (a swap of two letters counts as one edit)."""
    d = [[0] * (len(y) + 1) for _ in range(len(x) + 1)]
    for i in range(len(x) + 1):
        d[i][0] = i
    for j in range(len(y) + 1):
        d[0][j] = j
    for i in range(1, len(x) + 1):
        for j in range(1, len(y) + 1):
            cost = 0 if x[i - 1] == y[j - 1] else 1
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost)
            if i > 1 and j > 1 and x[i - 1] == y[j - 2] and x[i - 2] == y[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[len(x)][len(y)]


def _is_subsequence(short: list[str], long: list[str]) -> bool:
    it = iter(long)
    return len(short) < len(long) and all(word in it for word in short)
