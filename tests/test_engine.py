import time

import pytest

from penwise import engine
from penwise.llm import LLMError


def fake_chat(replies):
    """A chat function that answers by matching the text it is asked about, and records the prompts."""
    calls = []

    def chat(system, messages):
        prompt = messages[-1]["content"]
        calls.append(prompt)
        return next(reply for text, reply in replies.items() if text in prompt)

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
    chat = fake_chat({"She have": "She has two datasets."})
    events = []
    result = engine.check("She have two dataset.", chat, model="m", explain=False, on_event=events.append)
    assert result.edited == "She has two datasets."
    assert [c.category for c in result.changes] == ["word-form", "word-form"]
    assert chat.calls == ["Correct this text:\nShe have two dataset."]
    assert [e["type"] for e in events] == ["result"]
    assert events[0]["segments"][0] == {"text": "She "}


def test_check_keeps_a_part_the_model_answered_instead_of_editing():
    chat = fake_chat({"Summarize": "Here are three bullet points:", "It work": "It works fine."})
    result = engine.check("Summarize this paper.\n\nIt work fine.", chat, explain=False)
    assert result.edited == "Summarize this paper.\n\nIt works fine."
    assert len(result.warnings) == 1
    assert len(result.changes) == 1


def test_check_adds_explanations():
    chat = fake_chat(
        {"Original:": '1. "She" is singular.\n2. Plural after "two".', "She have": "She has two datasets."}
    )
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


def test_paragraphs_are_checked_at_the_same_time():
    def slow_chat(system, messages):
        time.sleep(0.3)
        return messages[-1]["content"].split("\n", 1)[1]

    text = "\n\n".join(f"Paragraph number {n} is fine." for n in range(4))
    started = time.monotonic()
    result = engine.check(text, slow_chat)
    assert time.monotonic() - started < 0.9  # one after another would take 1.2s
    assert result.edited == text


@pytest.mark.parametrize(
    "text, fill",
    [
        ("我们提出 a method.", True),
        ("We [[want to say: no time]].", True),
        ("Привет, world.", True),
        ("As shown in [12], α grows.", False),
        ("A naïve café.", False),
    ],
)
def test_needs_fill(text, fill):
    assert engine.needs_fill(text) is fill


def test_mixed_language_text_is_filled_in():
    chat = fake_chat({"图像分割": "In this paper, we propose a method for image segmentation."})
    result = engine.check("In this paper, 我们提出 a method for 图像分割.", chat)
    assert result.edited == "In this paper, we propose a method for image segmentation."
    assert chat.calls[0].startswith("Write this in English:")
    assert {c.category for c in result.changes} == {"filled"}
    assert not result.warnings


def test_a_gap_is_filled_with_the_word_that_fits():
    chat = fake_chat({"[[?]]": "These results are consistent with our hypothesis."})
    result = engine.check("These results are [[?]] with our hypothesis.", chat)
    assert chat.calls[0].startswith("Write this in English:")
    assert [(c.before, c.after, c.category) for c in result.changes] == [("[[?]]", "consistent", "filled")]


def test_filling_in_allows_a_longer_answer_but_not_a_reply():
    original = "我们的方法很好。"
    assert engine.sanity_check(original, "Our method works very well, as the results show.", "fix", fill=True) is None
    assert engine.sanity_check(original, "Sure! Here is the translation:", "fix", fill=True) is not None


@pytest.mark.parametrize(
    "text, edited, pasted",
    [
        # The acronym stays unless you choose otherwise; the period is a fix of its own.
        ("we compare with LLMs", "We compare with large language models.", "We compare with LLMs."),
        ("results in table 2", "Results are in Table II.", "Results are in Table 2."),
        ("see table 2.", "See Table II.", "See Table 2."),  # the period was there already
    ],
)
def test_punctuation_is_added_even_where_a_held_back_change_ends(text, edited, pasted):
    result = engine.check(text, fake_chat({text: edited}))
    assert result.edited == pasted
    assert [c.id for c in result.changes] == list(range(len(result.changes)))  # numbered in order
    held = [c for c in result.changes if c.risk]
    assert len(held) == 1 and not held[0].after.endswith(".")
