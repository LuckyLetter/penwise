from penwise import history
from penwise.diff import Change
from penwise.lessons import AGREEMENT_NOTE, NOTES


def accepted(before, after, category="spelling"):
    return {"before": before, "after": after, "category": category, "context_before": "the ", "context_after": " of"}


def test_record_and_mark_seen(tmp_path):
    path = tmp_path / "history.jsonl"
    assert history.record([accepted("teh", "the"), accepted("teh", "the"), accepted("x", "x")], path) == 2

    changes = [Change(id=0, before="Teh", after="The"), Change(id=1, before="in", after="on")]
    history.mark_seen(changes, path)
    assert [c.seen for c in changes] == [2, 0]


def test_history_keeps_only_short_snippets(tmp_path):
    path = tmp_path / "history.jsonl"
    history.record([accepted("teh", "the")], path)
    (entry,) = history.load(path)
    assert entry["context"] == "the [teh] of"
    assert set(entry) == {"time", "before", "after", "category", "context"}


def test_insights(tmp_path):
    path = tmp_path / "history.jsonl"
    history.record([accepted("in", "on", "preposition")] * 3 + [accepted("a", "an", "article")], path)
    data = history.insights(path)
    assert data["total"] == 4
    assert data["lessons"][0] == ("Prepositions", NOTES["preposition"], 3, "the [in] of")
    assert data["repeated"] == [("in → on", 3, "the [in] of")]


def test_clear(tmp_path):
    path = tmp_path / "history.jsonl"
    assert history.clear(path) is False
    history.record([accepted("a", "b")], path)
    assert history.clear(path) is True
    assert history.load(path) == []


def test_insights_name_the_grammar_point_from_the_words_around_the_fix(tmp_path):
    path = tmp_path / "history.jsonl"
    agreement = {"before": "are", "after": "is", "context_before": "Each of the models ", "context_after": " tested."}
    plural = {"before": "dataset", "after": "datasets", "context_before": "two ", "context_after": " and"}
    history.record([agreement, agreement, plural], path)
    assert history.insights(path)["lessons"] == [
        ("Subject–verb agreement", AGREEMENT_NOTE, 2, "Each of the models [are] tested."),
        ("Word form", NOTES["word-form"], 1, "two [dataset] and"),
    ]
