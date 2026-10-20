import pytest

from penwise import lessons
from penwise.diff import Change
from penwise.lessons import (
    A_AN_NOTE,
    COMMA_ADDED_NOTE,
    COMMA_REMOVED_NOTE,
    GAP_NOTE,
    LABELS,
    POSSESSIVE,
    SPLICE_NOTE,
    annotate,
    classify,
)


@pytest.mark.parametrize(
    "before, after, category",
    [
        ("teh", "the", "spelling"),
        ("avaiable", "available", "spelling"),
        ("form", "from", "spelling"),
        ("friday", "Friday", "capitalization"),
        ("However", "However,", "punctuation"),
        ("  ", " ", "spacing"),
        ("a", "the", "article"),
        ("", "the ", "article"),
        ("in", "on", "preposition"),
        ("Despite of", "Despite", "preposition"),
        ("result", "results", "word-form"),
        ("have", "has", "word-form"),
        ("go", "went", "word-form"),
        ("send", "sent", "word-form"),  # not a typo: Always keep "send" would be wrong
        ("bring", "brought", "word-form"),
        ("experiment", "experimental", "word-form"),  # not a typo either
        ("basic", "basically", "word-form"),
        ("casual", "causal", "spelling"),
        ("3", "4", "number"),
        ("1,000", "1,200", "number"),
        ("study", "studies", "word-form"),
        ("informations", "information", "uncountable"),
        ("then", "than", "confusable"),
        ("it's", "its", "confusable"),
        ("e.g.", "i.e.", "confusable"),
        ("big", "large", "word-choice"),
        ("", "very ", "added"),
        ("very ", "", "removed"),
        ("in order to", "to", "removed"),
        ("make a proposal of", "propose", "rephrased"),
        ("图像分割", "image segmentation", "filled"),
        ("[[show very clear]]", "clearly show", "filled"),
        ("[[?]]", "consistent", "filled"),
    ],
)
def test_classify(before, after, category):
    assert classify(before, after)[0] == category


def test_specific_notes():
    assert classify("a", "an")[1] == A_AN_NOTE
    assert classify("However", "However,")[1] == COMMA_ADDED_NOTE
    assert classify("model, is", "model is")[1] == COMMA_REMOVED_NOTE
    assert classify("works, it", "works; it")[1] == SPLICE_NOTE
    assert classify("[[?]]", "consistent")[1] == GAP_NOTE
    assert classify("[[ ? ]]", "express")[1] == GAP_NOTE


def test_annotate_sets_label_and_note():
    change = Change(id=0, before="dataset", after="datasets")
    annotate([change])
    assert change.category == "word-form"
    assert change.label == LABELS["word-form"]
    assert change.note


@pytest.mark.parametrize(
    "before, after",
    [("you", "your"), ("it", "Its"), ("we", "Our"), ("they", "their"), ("much", "many"), ("maybe", "may be")],
)
def test_pronouns_for_possessives_and_other_easily_mixed_words(before, after):
    category, note = classify(before, after)
    assert category == "confusable"
    if before in ("you", "it", "we", "they"):
        assert note == POSSESSIVE


@pytest.mark.parametrize(
    "before, after, context_before, context_after, note",
    [
        ("are", "is", "Each of the models ", " tested.", lessons.AGREEMENT_NOTE),
        ("This", "These", "", " results show it.", lessons.DEMONSTRATIVE_NOTE),
        ("found", "find", "We didn't ", " it.", lessons.BASE_FORM_NOTE),
        ("is depend", "depends", "It ", " on data.", lessons.BE_VERB_NOTE),
        ("has been", "was", "The method ", " proposed in 2019.", lessons.PAST_TIME_NOTE),
        ("more ", "", "This is ", "better.", lessons.DOUBLE_COMPARISON_NOTE),
        ("most ", "", "It is the ", "fastest model.", lessons.DOUBLE_COMPARISON_NOTE),
        ("but ", "", "Although it is fast, ", "it is large.", lessons.ALTHOUGH_BUT_NOTE),
        ("able to ", "", "The model can ", "learn.", lessons.CAN_ABLE_NOTE),
        ("went", "gone", "We have ", " there.", lessons.PERFECT_NOTE),
        ("finish", "finished", "It has ", " now.", lessons.PERFECT_NOTE),
        ("use", "used", "It is ", " widely.", lessons.PASSIVE_NOTE),
        ("improve", "improving", "A method for ", " it.", lessons.GERUND_NOTE),
        ("use", "using", "We start by ", " it.", lessons.GERUND_NOTE),
        ("send", "sent", "Hi Ann, I ", " you the report yesterday.", lessons.PAST_TIME_NOTE),
        ("go", "went", "Two years ago we ", " there.", lessons.PAST_TIME_NOTE),
        ("propose", "proposed", "It was first ", " in 2019.", lessons.PAST_TIME_NOTE),
        ("use", "used", "It is ", " widely since last year.", lessons.PASSIVE_NOTE),  # passive comes first
        ("hear", "hearing", "I look forward to ", " from you.", lessons.FORWARD_TO_NOTE),
        ("work", "working", "I'm used to ", " late.", lessons.FORWARD_TO_NOTE),
        ("will ", "", "I will call you when I ", "arrive.", lessons.FUTURE_AFTER_WHEN_NOTE),
        ("will arrive", "arrive", "Tell me as soon as it ", ".", lessons.FUTURE_AFTER_WHEN_NOTE),
        ("go", "goes", "He ", " to school by bus.", lessons.THIRD_PERSON_NOTE),
        ("depend", "depends", "It's ", " on the weather.", lessons.THIRD_PERSON_NOTE),
        ("It's", "It", "", " depend on the weather.", lessons.BE_VERB_NOTE),
        (" am", "", "I", " agree with you.", lessons.BE_VERB_NOTE),
        ("students", "student", "Every ", " has a laptop.", lessons.EVERY_NOTE),
        ("am", "have been", "I ", " working here since 2019.", lessons.SINCE_FOR_NOTE),
        ("will ", "", "In this paper, we ", "introduce a dataset.", lessons.PAPER_PRESENT_NOTE),
        ("to note", "noting", "It is worth ", " that it converges.", lessons.WORTH_NOTE),
        (",", ".", "Thanks for your quick reply", " I will check it.", lessons.SPLICE_NOTE),
    ],
)
def test_common_grammar_points_get_their_own_note(before, after, context_before, context_after, note):
    assert classify(before, after, context_before, context_after)[1] == note


@pytest.mark.parametrize(
    "before, after, context_before, context_after",
    [
        ("improve", "improving", "We contribute to ", " it."),  # away from the base form
        ("but ", "", "It is fast, ", "it is large."),  # no "although"
        ("more ", "", "We need ", "data."),  # not a comparative
        ("is used", "uses", "It ", " here."),  # passive to active
        ("send", "sent", "Please ", " it to me."),  # no finished time
        ("sent", "send", "I ", " it yesterday."),  # away from the past
        ("will ", "", "I ", "call you tomorrow."),  # the future, rightly
        ("hear", "hearing", "I want to ", " it."),  # "to" before a verb
        ("am", "", "I ", " happy."),  # not before a verb
        ("go", "goes", "They ", " home."),  # not he/she/it
        ("go", "goes", "He ", " home."),  # no rule of its own here: the general word-form note
    ],
)
def test_the_grammar_notes_stay_out_of_other_changes(before, after, context_before, context_after):
    note = classify(before, after, context_before, context_after)[1]
    grammar = {
        lessons.BASE_FORM_NOTE,
        lessons.ALTHOUGH_BUT_NOTE,
        lessons.DOUBLE_COMPARISON_NOTE,
        lessons.BE_VERB_NOTE,
        lessons.PERFECT_NOTE,
        lessons.PASSIVE_NOTE,
        lessons.GERUND_NOTE,
    }
    assert note not in grammar


def test_each_grammar_point_has_a_short_title():
    assert lessons.label("removed", lessons.FUTURE_AFTER_WHEN_NOTE) == "No “will” after when/if"
    assert lessons.label("punctuation", SPLICE_NOTE) == "Joining two sentences"
    assert lessons.label("punctuation", COMMA_ADDED_NOTE) == "Commas"
    assert lessons.label("punctuation", COMMA_REMOVED_NOTE) == "Commas"
