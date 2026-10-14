import pytest

from penwise.diff import apply, diff, similarity, tokenize

PAIRS = [
    ("She have two dataset.", "She has two datasets."),
    ("However the method works", "However, the method works"),
    ("We go school every day", "We go to school every day"),
    ("It is very very good.", "It is very good."),
    ("  leading and trailing space \n", "  leading and trailing spaces \n"),
    ("Line one\nline too", "Line one\nline two"),
    ("", "Something new."),
    ("We [[want to say: no time]] to run more.", "We had no time to run more."),
    ("如上所述, 这个问题 is still open.", "As noted above, this issue remains open."),
    ("Unchanged text.", "Unchanged text."),
]


@pytest.mark.parametrize("text", ["Hello, world!", "don't stop", "a\n\nb  c", "naïve café ✓", ""])
def test_tokens_join_back_to_the_text(text):
    assert "".join(tokenize(text)) == text


@pytest.mark.parametrize("original, edited", PAIRS)
def test_applying_all_or_no_changes_rebuilds_each_text(original, edited):
    segments, changes = diff(original, edited)
    assert apply(segments, changes) == edited
    assert apply(segments, changes, accepted=set()) == original


def test_undoing_one_change_keeps_the_others():
    segments, changes = diff("She have two dataset.", "She has two datasets.")
    assert [(c.before, c.after) for c in changes] == [("have", "has"), ("dataset", "datasets")]
    assert apply(segments, changes, accepted={changes[1].id}) == "She have two datasets."


def test_line_breaks_are_never_changed():
    original = "First line\nsecond line has a eror"
    edited = "First line second line has an error"
    segments, changes = diff(original, edited)
    assert apply(segments, changes) == "First line\nsecond line has an error"
    assert all("\n" not in c.before for c in changes)


def test_separate_small_fixes_stay_separate():
    _, changes = diff("teh resluts", "the results")
    assert [(c.before, c.after) for c in changes] == [("teh", "the"), ("resluts", "results")]


def test_a_reworded_phrase_is_one_change():
    _, changes = diff("robustness of LLMs agains attacks", "robustness of Large Language Models against attacks")
    assert [(c.before, c.after) for c in changes] == [("LLMs agains", "Large Language Models against")]


def test_changes_carry_nearby_words_as_context():
    _, changes = diff(
        "We evaluate our approach on three benchmark today.", "We evaluate our approach on three benchmarks today."
    )
    (change,) = changes
    assert change.context_before.endswith("on three ")
    assert change.context_after == " today."


def test_ids_start_at_first_id():
    _, changes = diff("a eror", "an error", first_id=5)
    assert [c.id for c in changes] == [5, 6]


def test_similarity():
    assert similarity("The cat sat on the mat today.", "The cat sat on the mat today.") == 1
    assert similarity("Please summarize this paper for me now.", "Here are three bullet points about it.") < 0.3


def test_a_note_in_double_brackets_is_one_change():
    _, changes = diff("We [[want to say: no time]] to run more.", "We had no time to run more.")
    assert [(c.before.strip(), c.after.strip()) for c in changes] == [("[[want to say: no time]]", "had no time")]


def test_filled_in_words_join_their_neighbours():
    _, changes = diff("As shown in [12], 这个问题 is still open.", "As shown in [12], this issue remains open.")
    assert [(c.before, c.after) for c in changes] == [("这个问题 is still", "this issue remains")]


def test_an_untouched_note_is_not_a_change():
    assert diff("Keep [[this]] here.", "Keep [[this]] here.")[1] == []
