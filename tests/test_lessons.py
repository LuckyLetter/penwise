import pytest

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
