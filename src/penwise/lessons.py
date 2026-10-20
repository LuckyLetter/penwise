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
    {"send", "sends", "sent", "sending"},
    {"spend", "spends", "spent", "spending"},
    {"build", "builds", "built", "building"},
    {"get", "gets", "got", "gotten", "getting"},
    {"begin", "begins", "began", "begun", "beginning"},
    {"bring", "brings", "brought", "bringing"},
    {"buy", "buys", "bought", "buying"},
    {"think", "thinks", "thought", "thinking"},
    {"teach", "teaches", "taught", "teaching"},
    {"seek", "seeks", "sought", "seeking"},
    {"keep", "keeps", "kept", "keeping"},
    {"leave", "leaves", "left", "leaving"},
    {"meet", "meets", "met", "meeting"},
    {"pay", "pays", "paid", "paying"},
    {"say", "says", "said", "saying"},
    {"tell", "tells", "told", "telling"},
    {"feel", "feels", "felt", "feeling"},
    {"hold", "holds", "held", "holding"},
    {"know", "knows", "knew", "known", "knowing"},
    {"grow", "grows", "grew", "grown", "growing"},
    {"draw", "draws", "drew", "drawn", "drawing"},
    {"run", "runs", "ran", "running"},
    {"come", "comes", "came", "coming"},
    {"become", "becomes", "became", "becoming"},
    {"rise", "rises", "rose", "risen", "rising"},
    {"fall", "falls", "fell", "fallen", "falling"},
    {"speak", "speaks", "spoke", "spoken", "speaking"},
    {"break", "breaks", "broke", "broken", "breaking"},
    {"forget", "forgets", "forgot", "forgotten", "forgetting"},
    {"understand", "understands", "understood", "understanding"},
    {"stand", "stands", "stood", "standing"},
    {"lose", "loses", "lost", "losing"},
    {"win", "wins", "won", "winning"},
    {"hear", "hears", "heard", "hearing"},
    {"mean", "means", "meant", "meaning"},
    {"sell", "sells", "sold", "selling"},
    {"sit", "sits", "sat", "sitting"},
    {"drive", "drives", "drove", "driven", "driving"},
    {"eat", "eats", "ate", "eaten", "eating"},
    {"fly", "flies", "flew", "flown", "flying"},
    {"throw", "throws", "threw", "thrown", "throwing"},
    {"this", "these"},
    {"that", "those"},
]

INFLECTION_ENDINGS = {"", "s", "es", "ed", "d", "ing", "y", "ies", "ied", "er", "est", "ly", "e"}
# Endings that make another word from the same root: experiment → experimental, basic → basically.
DERIVED_ENDINGS = {"al", "ally", "ic", "ical", "ically", "ion", "ions", "ive", "ness", "ity", "ment", "ments"}

# Irregular past forms (went, sent), for "yesterday I send it" → "sent".
IRREGULAR_PAST = {
    "was", "were", "had", "did", "went", "made", "took", "gave", "wrote", "showed", "found", "saw", "chose", "led",
    "sent", "spent", "built", "got", "began", "brought", "bought", "thought", "taught", "sought", "kept", "left",
    "met", "paid", "said", "told", "felt", "held", "knew", "grew", "drew", "ran", "came", "became", "rose", "fell",
    "spoke", "broke", "forgot", "understood", "stood", "lost", "won", "heard", "meant", "sold", "sat", "drove",
    "ate", "flew", "threw",
}  # fmt: skip
# A time that is over: what happened then takes the past tense.
FINISHED_TIME = re.compile(
    r"\b(yesterday|ago|last (week|month|year|night|time|summer|winter|spring|autumn|fall|semester|term)"
    r"|in (1[89]|20)\d\d)\b",
    re.IGNORECASE,
)
NUMBER = re.compile(r"[\d.,%]*\d[\d.,%]*")

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

POSSESSIVE = "“our method”, “its accuracy”, “their results”: a possessive (my, your, its, our, their, his, her) before a noun shows whose it is."

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
    frozenset({"many", "much"}): "“many” for things you can count (many samples); “much” for amounts (much data).",
    frozenset({"maybe", "may be"}): "“maybe” = perhaps (Maybe it works); “may be” is the verb (It may be faster).",
    frozenset({"whether", "weather"}): "“whether” introduces a choice (whether it works); “weather” is rain and sun.",
    frozenset({"quite", "quiet"}): "“quite” = fairly or very (quite fast); “quiet” = not loud.",
    # A pronoun where its possessive belongs, as in "we method", "it accuracy".
    **{
        frozenset(pair): POSSESSIVE
        for pair in (("you", "your"), ("it", "its"), ("they", "their"), ("we", "our"), ("he", "his"), ("she", "her"))
    },
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
    "number": "Number",
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
    "number": "A different number: check which one is right.",
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

# Grammar points common in research writing by non-native speakers, each with its own note.
AGREEMENT_NOTE = "The verb agrees with its subject: the result is, the results are, each of the models is."
DEMONSTRATIVE_NOTE = "“this/that” go with a singular noun, “these/those” with a plural one: this result, these results."
BASE_FORM_NOTE = "After do/does/did, can, will, should, must or “to”, use the verb's base form: didn't find, can learn."
BE_VERB_NOTE = "No “is/are” before a main verb in the present tense: it depends, they need (not it is depend)."
PAST_TIME_NOTE = "With a finished time (in 2019, last year), use the past tense: it was proposed in 2019."
DOUBLE_COMPARISON_NOTE = (
    "“better” and “fastest” already compare: no “more” or “most” before them (better, not more better)."
)
ALTHOUGH_BUT_NOTE = (
    "“Although” and “but” don't go together: use one (Although it is fast, it is large / It is fast, but it is large)."
)
CAN_ABLE_NOTE = "“can” and “be able to” mean the same: use one (it can learn, or it is able to learn)."
PERFECT_NOTE = "After have/has/had, use the past participle: we have gone, it has finished (not have went)."
PASSIVE_NOTE = "In the passive, “is/are/was/were” takes the past participle: it is used, they were compared."
GERUND_NOTE = "After a preposition (for, by, before, without…), a verb takes -ing: for improving, by using."
WORTH_NOTE = "“worth” takes the -ing form: it is worth noting, worth trying."
PAPER_PRESENT_NOTE = (
    "A paper describes itself in the present tense: In this paper, we introduce… (not we will introduce)."
)
FORWARD_TO_NOTE = (
    "In “look forward to”, “be used to” and “when it comes to”, “to” is a preposition: "
    "the verb takes -ing (I look forward to hearing from you)."
)
FUTURE_AFTER_WHEN_NOTE = (
    "After when, if, before, after, until or as soon as, the present tense speaks of the future: "
    "when I arrive (not when I will arrive)."
)
THIRD_PERSON_NOTE = "After he, she or it, a present-tense verb ends in -s: he goes, it depends."
EVERY_NOTE = "“every” and “each” go with one thing: every student, each result (and every student has)."
SINCE_FOR_NOTE = (
    "For something that began in the past and still goes on, with since or for, use have/has been: "
    "I have been working here since 2019."
)
AGREEMENT = [{"is", "are"}, {"was", "were"}, {"has", "have"}, {"does", "do"}, {"doesn't", "don't"}, {"isn't", "aren't"}]
DEMONSTRATIVES = [{"this", "these"}, {"that", "those"}]
BASE_FORM_AFTER = {
    "do",
    "does",
    "did",
    "don't",
    "doesn't",
    "didn't",
    "can",
    "can't",
    "cannot",
    "could",
    "couldn't",
    "will",
    "won't",
    "would",
    "should",
    "must",
    "may",
    "might",
    "to",
}
COMPARATIVES = {"better", "best", "worse", "worst", "less", "least", "more", "most"}
HAVE = {"have", "has", "had", "having"}
BE = {"is", "are", "was", "were", "be", "been", "being", "am"}
# Verbs that are never "I am agree": no "is/are" before them.
STATIVE = {
    "agree", "disagree", "depend", "believe", "know", "need", "want", "like", "prefer", "mean", "think",
    "suggest", "consist", "belong", "contain", "understand", "hope", "seem", "exist", "include", "require",
}  # fmt: skip
FORWARD_TO = re.compile(r"\b(forward|used|accustomed|comes|committed|devoted|object|objected)\s+to\s*$", re.IGNORECASE)
PAPER = re.compile(r"\b(in )?this (paper|work|study|article|thesis|chapter|section)\b", re.IGNORECASE)
FUTURE_AFTER = re.compile(r"\b(when|if|before|after|until|unless|once|as soon as)\s+[\w']+\s*$", re.IGNORECASE)
PARTICIPLES = {
    "been",
    "done",
    "gone",
    "made",
    "taken",
    "given",
    "written",
    "shown",
    "found",
    "seen",
    "chosen",
    "led",
    "had",
}

# Short titles for the points with a note of their own, in the panel and in "Your recurring fixes".
RULE_TITLES = {
    AGREEMENT_NOTE: "Subject–verb agreement",
    DEMONSTRATIVE_NOTE: "this/these, that/those",
    BASE_FORM_NOTE: "Base form of the verb",
    BE_VERB_NOTE: "No “is” before a verb",
    PAST_TIME_NOTE: "Past tense",
    DOUBLE_COMPARISON_NOTE: "Double comparison",
    ALTHOUGH_BUT_NOTE: "Although … but",
    CAN_ABLE_NOTE: "can / be able to",
    POSSESSIVE: "Possessives",
    PERFECT_NOTE: "Past participle after have",
    PASSIVE_NOTE: "Passive",
    GERUND_NOTE: "-ing after a preposition",
    A_AN_NOTE: "a or an",
    FORWARD_TO_NOTE: "look forward to + -ing",
    WORTH_NOTE: "worth + -ing",
    PAPER_PRESENT_NOTE: "Present tense in a paper",
    FUTURE_AFTER_WHEN_NOTE: "No “will” after when/if",
    THIRD_PERSON_NOTE: "he/she/it + -s",
    EVERY_NOTE: "every/each + one thing",
    SINCE_FOR_NOTE: "since/for + have been",
    SPLICE_NOTE: "Joining two sentences",
    COMMA_ADDED_NOTE: "Commas",
    COMMA_REMOVED_NOTE: "Commas",
    HYPHEN_NOTE: "Hyphens",
    APOSTROPHE_NOTE: "Apostrophes",
}


def words(text: str) -> list[str]:
    return [w.lower().replace("’", "'") for w in WORD.findall(text)]


def classify(before: str, after: str, context_before: str = "", context_after: str = "") -> tuple[str, str]:
    """Return (category, note) for one change; the text around it helps name some grammar points."""
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

    if bw and aw and all(NUMBER.fullmatch(w) for w in bw + aw):
        return "number", NOTES["number"]
    key = frozenset({" ".join(bw), " ".join(aw)})
    if len(key) == 2 and key in CONFUSABLE:
        return "confusable", CONFUSABLE[key]
    grammar = _grammar_point(
        bw, aw, words(context_before)[-1:], words(context_after)[:1], context_before, context_after
    )
    if grammar:
        return grammar

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


def label(category: str, note: str) -> str:
    """The title for a change: the grammar point when it has a note of its own, else its kind."""
    return RULE_TITLES.get(note, LABELS[category])


def annotate(changes: list[Change]) -> None:
    for change in changes:
        change.category, change.note = classify(
            change.before, change.after, change.context_before, change.context_after
        )
        change.label = label(change.category, change.note)


def _grammar_point(
    bw: list[str],
    aw: list[str],
    previous: list[str],
    following: list[str],
    context_before: str,
    context_after: str = "",
):
    """(category, note) for a grammar point that has a note of its own, or None."""
    if len(bw) == 1 and len(aw) == 1:
        x, y = bw[0], aw[0]
        if {x, y} in AGREEMENT:
            return "word-form", AGREEMENT_NOTE
        if {x, y} in DEMONSTRATIVES:
            return "word-form", DEMONSTRATIVE_NOTE
        before_word = previous[0] if previous else ""
        adds_s = _same_word(x, y) and y.endswith("s") and not x.endswith("s")
        if adds_s and before_word in ("he", "she", "it", "he's", "she's", "it's"):  # he go → goes
            return "word-form", THIRD_PERSON_NOTE
        if before_word in ("every", "each") and _same_word(x, y) and x.endswith("s") and not y.endswith("s"):
            return "word-form", EVERY_NOTE
        # It's depend → It depends: the "is" goes.
        contraction = re.fullmatch(r"(\w+)'(s|re|m)", x)
        if contraction and y == contraction[1] and following and following[0] in STATIVE:
            return "removed", BE_VERB_NOTE
        if FORWARD_TO.search(context_before) and _same_word(x, y) and y.endswith("ing") and not x.endswith("ing"):
            return "word-form", FORWARD_TO_NOTE
        # didn't found → didn't find; but not "contribute to improve" → "to improving".
        to_base_form = _same_word(x, y) and len(y) <= len(x) and not y.endswith("ing")
        if previous and previous[0] in BASE_FORM_AFTER and to_base_form:
            return "word-form", BASE_FORM_NOTE
        before_it = previous[0] if previous else ""
        participle = x != y and _same_word(x, y) and (y in PARTICIPLES or y.endswith("ed"))
        if participle and (before_it in HAVE or before_it.endswith("'ve")):  # have went → gone
            return "word-form", PERFECT_NOTE
        if participle and before_it in BE:  # is use → used
            return "word-form", PASSIVE_NOTE
        # Yesterday I send it → sent: a finished time takes the past tense.
        finished = FINISHED_TIME.search(f"{context_before} {context_after}")
        if finished and x != y and _same_word(x, y) and _past(y) and not _past(x):
            return "word-form", PAST_TIME_NOTE
        # for improve → improving; "to" usually wants the base form instead.
        if before_it in PREPOSITIONS - {"to"} and _same_word(x, y) and y.endswith("ing") and not x.endswith("ing"):
            return "word-form", GERUND_NOTE
    # "is depend" → "depends"; "is used" → "uses" is another matter.
    be_verb = len(bw) == 2 and bw[0] in ("is", "are", "am") and not bw[1].endswith(("ed", "en"))
    if be_verb and len(aw) == 1 and _same_word(bw[1], aw[0]):
        return "word-form", BE_VERB_NOTE
    if bw in (["has", "been"], ["have", "been"]) and aw in (["was"], ["were"]):
        return "word-form", PAST_TIME_NOTE
    # I am working here since 2019 → have been working.
    since = re.search(r"\b(since|for)\b", context_after, re.IGNORECASE)
    if since and bw in (["am"], ["is"], ["are"]) and aw in (["have", "been"], ["has", "been"]):
        return "word-form", SINCE_FOR_NOTE
    # when I will arrive → when I arrive
    if bw[:1] == ["will"] and aw == bw[1:] and FUTURE_AFTER.search(context_before):
        return "removed", FUTURE_AFTER_WHEN_NOTE
    # In this paper, we will introduce → we introduce
    if bw[:1] == ["will"] and aw == bw[1:] and PAPER.search(context_before):
        return "removed", PAPER_PRESENT_NOTE
    # worth to note → worth noting
    worth = len(bw) == 2 and bw[0] == "to" and len(aw) == 1 and aw[0].endswith("ing") and _same_word(bw[1], aw[0])
    if worth and re.search(r"\bworth\s*$", context_before, re.IGNORECASE):
        return "word-form", WORTH_NOTE
    if aw:
        return None
    if bw in (["am"], ["is"], ["are"]) and following and following[0] in STATIVE:  # I am agree
        return "removed", BE_VERB_NOTE
    if (
        bw in (["more"], ["most"])
        and following
        and (following[0] in COMPARATIVES or following[0].endswith(("er", "est")))
    ):
        return "removed", DOUBLE_COMPARISON_NOTE
    if bw == ["but"] and re.search(r"\b(al)?though\b", context_before, re.IGNORECASE):
        return "removed", ALTHOUGH_BUT_NOTE
    if bw in (["able", "to"], ["be", "able", "to"]) and previous and previous[0] in ("can", "could", "cannot", "can't"):
        return "removed", CAN_ABLE_NOTE
    return None


def _past(word: str) -> bool:
    return word in IRREGULAR_PAST or word.endswith("ed")


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
    endings = INFLECTION_ENDINGS | DERIVED_ENDINGS if prefix >= 4 else INFLECTION_ENDINGS
    return prefix >= 2 and x[prefix:] in endings and y[prefix:] in endings


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
