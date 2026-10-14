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
