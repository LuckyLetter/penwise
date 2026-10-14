import pytest

from penwise import engine
from penwise.protect import risk


@pytest.mark.parametrize(
    "before, after, expected",
    [
        ("dataset", "datasets", None),
        ("shown in [12],", "shown,", "a citation"),
        ("92%", "95%", "a number"),
        ("3 times", "three times", "a number"),
        ("LLMs", "Large Language Models", "an acronym"),
        ("$\\alpha$", "alpha", "math"),
        ("`run()`", "run", "code"),
        ("https://example.org", "the website", "a link"),
        ("in [12]", "on [12]", None),  # the citation is still there
        ("the GPU", "a GPU", None),
        ("ai", "AI", None),  # adding an acronym is fine
    ],
)
def test_risk(before, after, expected):
    assert risk(before, after) == expected


def test_risky_changes_are_suggested_but_not_applied():
    original = "As shown in [12], the model achieve 92% accuracy."
    edited = "As shown, the model achieves 92% accuracy."
    result = engine.check(original, lambda system, messages: edited)
    assert [(c.before.strip(" ,"), c.risk) for c in result.changes] == [("in [12]", "a citation"), ("achieve", None)]
    assert result.edited == "As shown in [12], the model achieves 92% accuracy."
    assert result.to_dict()["changes"][0]["risk"] == "a citation"


def test_words_you_keep_are_never_changed():
    assert risk("Pytorch", "PyTorch", keep=["Pytorch"]) == "“Pytorch”, a word you keep"
    assert risk("the Pytorch model", "the Pytorch models", keep=["Pytorch"]) is None
    result = engine.check("We use Pytorch models.", lambda s, m: "We use PyTorch models.", keep=["Pytorch"])
    assert result.edited == "We use Pytorch models."
