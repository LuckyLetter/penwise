from penwise import history
from penwise.diff import Change


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
    assert data["categories"][0] == ("preposition", 3)
    assert data["repeated"] == [("in → on", 3, "the [in] of")]


def test_clear(tmp_path):
    path = tmp_path / "history.jsonl"
    assert history.clear(path) is False
    history.record([accepted("a", "b")], path)
    assert history.clear(path) is True
    assert history.load(path) == []
