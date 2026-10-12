import pytest

from penwise.diff import Change
from penwise.lessons import A_AN_NOTE, COMMA_ADDED_NOTE, LABELS, annotate, classify


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
    ],
)
def test_classify(before, after, category):
    assert classify(before, after)[0] == category


def test_specific_notes():
    assert classify("a", "an")[1] == A_AN_NOTE
    assert classify("However", "However,")[1] == COMMA_ADDED_NOTE


def test_annotate_sets_label_and_note():
    change = Change(id=0, before="dataset", after="datasets")
    annotate([change])
    assert change.category == "word-form"
    assert change.label == LABELS["word-form"]
    assert change.note
