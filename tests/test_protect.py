import pytest

from penwise import engine
from penwise.protect import risk, risk_in


@pytest.mark.parametrize(
    "before, after, expected",
    [
        ("dataset", "datasets", None),
        ("shown in [12],", "shown,", "a citation"),
        ("92%", "95%", "a number"),
        ("3 times", "three times", "a number"),
        ("LLMs", "Large Language Models", "an acronym"),
        ("$\\alpha$", "alpha", "math"),
        ("\\ref{fig:arch}", "\\ref{fig:archi}", "LaTeX"),
        ("\\cite{smith}", "Smith", "LaTeX"),
        ("/Users/ann/data/train.csv", "/Users/ann/data/Train.csv", "a file path"),
        ("C:\\Data\\raw", "C:\\Data\\Raw", "a file path"),
        ("--max-tokens", "--max_tokens", "code"),
        ("well-known", "well known", None),  # a hyphen in a word isn't an option
        ("and/or", "or", None),  # nor a slash a path
        ("`run()`", "run", "code"),
        ("https://example.org", "the website", "a link"),
        ("in [12]", "on [12]", None),  # the citation is still there
        ("the GPU", "a GPU", None),
        ("ai", "AI", None),  # adding an acronym is fine
        ("(Smith et al., 2020)", "(Smith et al. 2020)", "a citation"),
        ("Smith et al. (2020)", "Smith et al. (2021)", "a citation"),
        ("get_data", "getData", "code"),
        ("load()", "load", "code"),
        ("(see above)", "(see below)", None),  # brackets alone aren't a citation
        ("[1,2]", "[1, 2]", None),  # spaces in a citation don't change it
        ("1,000", "1,200", "a number"),
        ("1,000 samples", "1000 samples", "a number"),
        ("$a+b$", "$a + b$", None),  # nor in a formula
        ("`a b`", "`ab`", "code"),  # but they do in code
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


@pytest.mark.parametrize(
    "original, edited, kind",
    [
        ("See https://example.com/a_b for it.", "See https://example.com/a-b for it.", "a link"),
        ("Email ann@uni.edu today.", "Email ann@uni.ac.uk today.", "a link"),
        ("Run `pip install foo` first.", "Run `pip install bar` first.", "code"),
        ("As shown by (Smith et al., 2020), it works.", "As shown by (Smith et al. 2020), it works.", "a citation"),
        ("Prior work [3, 5] shows it.", "Prior work [3, 6] shows it.", "a citation"),
        (
            "Read https://github.com/LuckyLetter/penwise/blob/main/README.md now.",
            "Read https://github.com/LuckyLetter/penwise/blob/main/readme.md now.",
            "a link",  # a long one, too
        ),
    ],
)
def test_a_change_to_part_of_a_link_code_or_citation_is_held(original, edited, kind):
    result = engine.check(original, lambda system, messages: edited)
    assert [c.risk for c in result.changes] == [kind]
    assert result.edited == original


def test_changes_next_to_a_link_are_judged_on_their_own():
    original = "See https://example.org, it explain it."
    result = engine.check(original, lambda s, m: "See https://example.org; it explains it.")
    assert [c.risk for c in result.changes] == [None, None]
    assert risk_in("a b", 1, 2, "") is None
    result = engine.check("Write to ann@uni.edu", lambda s, m: "Write to ann@uni.edu.")
    assert [c.risk for c in result.changes] == [None]  # the full stop isn't part of the address


def test_a_change_inside_a_latex_reference_or_a_path_is_held():
    for original, edited, kind in [
        ("As shown in Figure \\ref{fig:arch}, it works.", "As shown in Figure \\ref{fig:archi}, it works.", "LaTeX"),
        ("The file is /Users/ann/data/train.csv now.", "The file is /Users/ann/data/Train.csv now.", "a file path"),
        ("Call it with --max-tokens.", "Call it with --max_tokens.", "code"),
    ]:
        result = engine.check(original, lambda s, m, edited=edited: edited)
        assert [c.risk for c in result.changes] == [kind], original
    result = engine.check("Read ~/notes/todo.txt.", lambda s, m: "Read ~/notes/todo.txt!")
    assert [c.risk for c in result.changes] == [None]  # the full stop isn't part of the path
