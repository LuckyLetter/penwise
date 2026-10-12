import pytest

from penwise import engine
from penwise.llm import LLMError


def fake_chat(replies):
    """A chat function that returns canned replies in order and records the prompts."""
    calls = []

    def chat(system, messages):
        calls.append(messages[-1]["content"])
        return replies.pop(0)

    chat.calls = calls
    return chat


@pytest.mark.parametrize(
    "text",
    [
        "One paragraph.",
        "  First.\n\nSecond paragraph.\n\n\n  Third.  \n",
        "Line one\nline two\n\nNext",
        "",
        "\n\n",
    ],
)
def test_split_joins_back_and_edits_only_trimmed_text(text):
    parts = engine.split(text)
    assert "".join(piece for piece, _ in parts) == text
    for piece, editable in parts:
        if editable:
            assert piece == piece.strip() and piece
        else:
            assert not piece.strip()


def test_split_sends_paragraphs_separately():
    parts = engine.split("First paragraph.\n\nSecond paragraph.")
    assert [p for p, editable in parts if editable] == ["First paragraph.", "Second paragraph."]


def test_split_breaks_long_paragraphs_at_sentences():
    sentence = "This is a fairly ordinary sentence about results. "
    text = (sentence * 10).strip()
    parts = engine.split(text, max_chars=120)
    editable = [p for p, e in parts if e]
    assert len(editable) > 1
    assert all(len(p) <= 120 for p in editable)
    assert "".join(p for p, _ in parts) == text


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Here is the corrected text:\nShe has two datasets.", "She has two datasets."),
        ('"She has two datasets."', "She has two datasets."),
        ("```\nShe has two datasets.\n```", "She has two datasets."),
        ("<think>hmm</think>\nShe has two datasets.", "She has two datasets."),
        ("Correct this text: She has two datasets.", "She has two datasets."),
        ("Corrected: She has two datasets.", "She has two datasets."),
        ("She has two datasets.\n\nNote: I changed the verb.", "She has two datasets."),
        ("She’s got “two” datasets.", 'She\'s got "two" datasets.'),
    ],
)
def test_clean(raw, expected):
    assert engine.clean(raw, "She have two dataset.") == expected


def test_clean_keeps_quotes_the_writer_used():
    assert engine.clean('"Quoted."', '"Quoted"') == '"Quoted."'


@pytest.mark.parametrize(
    "edited, rejected",
    [
        ("She has two datasets, and both are public on our website.", False),
        ("", True),
        ("Here are three bullet points about the paper:", True),
        ("Sure! I can help with that.", True),
        ("Completely unrelated words appear here instead of yours.", True),
    ],
)
def test_sanity_check(edited, rejected):
    original = "She have two dataset, and both are public on our website."
    assert (engine.sanity_check(original, edited, "fix") is not None) == rejected


def test_check_returns_changes_and_events():
    chat = fake_chat(["She has two datasets."])
    events = []
    result = engine.check("She have two dataset.", chat, model="m", explain=False, on_event=events.append)
    assert result.edited == "She has two datasets."
    assert [c.category for c in result.changes] == ["word-form", "word-form"]
    assert chat.calls == ["Correct this text:\nShe have two dataset."]
    assert [e["type"] for e in events] == ["result"]
    assert events[0]["segments"][0] == {"text": "She "}


def test_check_keeps_a_part_the_model_answered_instead_of_editing():
    chat = fake_chat(["Here are three bullet points:", "It works fine."])
    result = engine.check("Summarize this paper.\n\nIt work fine.", chat, explain=False)
    assert result.edited == "Summarize this paper.\n\nIt works fine."
    assert len(result.warnings) == 1
    assert len(result.changes) == 1


def test_check_adds_explanations():
    chat = fake_chat(["She has two datasets.", '1. "She" is singular.\n2. Plural after "two".'])
    events = []
    result = engine.check("She have two dataset.", chat, explain=True, on_event=events.append)
    assert [c.reason for c in result.changes] == ['"She" is singular.', 'Plural after "two".']
    assert events[-1] == {"type": "explanations", "reasons": {"0": '"She" is singular.', "1": 'Plural after "two".'}}


def test_explanation_failures_never_lose_the_edit():
    def chat(system, messages):
        if messages[-1]["content"].startswith("Original:"):
            raise LLMError("model went away")
        return "She has two datasets."

    result = engine.check("She have two dataset.", chat, explain=True)
    assert result.edited == "She has two datasets."
    assert all(c.reason is None for c in result.changes)


def test_parse_reasons_maps_numbers_to_ids():
    raw = "Sure:\n1. First reason.\n2) **Second** reason.\n7. Out of range."
    assert engine.parse_reasons(raw, [10, 11]) == {10: "First reason.", 11: "Second reason."}
