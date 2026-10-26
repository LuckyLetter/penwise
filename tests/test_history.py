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
    title, note, count, newest = data["lessons"][0]
    assert (title, note, count, newest["context"]) == ("Prepositions", NOTES["preposition"], 3, "the [in] of")
    [(pair, count, newest)] = data["repeated"]
    assert (pair, count, newest["after"]) == ("in → on", 3, "on")


def test_only_mistakes_count_each_with_an_example_as_you_wrote_it(tmp_path):
    path = tmp_path / "history.jsonl"
    reworded = {"before": "very important", "after": "crucial", "context_before": "It is ", "context_after": "."}
    filled = {"before": "[[?]]", "after": "pipeline", "context_before": "our ", "context_after": " runs"}
    article = {"before": "a", "after": "an", "context_before": "is ", "context_after": " LLM"}
    history.record([reworded, filled, article], path)
    data = history.insights(path)
    assert data["total"] == 1  # an Improve rewording and a phrase Penwise wrote aren't mistakes
    assert [title for title, *_ in data["lessons"]] == ["a or an"]
    shown = {"before_text": "is ", "before": "a", "after": "an", "after_text": " LLM"}
    assert history.example(data["lessons"][0][3]) == shown
    assert history.example({"before": "x", "after": "y", "context": "cut off [x"}) is None


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
    assert [(title, note, n, newest["context"]) for title, note, n, newest in history.insights(path)["lessons"]] == [
        ("Subject–verb agreement", AGREEMENT_NOTE, 2, "Each of the models [are] tested."),
        ("Word form", NOTES["word-form"], 1, "two [dataset] and"),
    ]


def test_a_damaged_history_never_stops_a_check(tmp_path):
    path = tmp_path / "history.jsonl"
    history.record([{"before": "untill", "after": "until", "category": "spelling"}] * 2, path)
    with path.open("ab") as file:
        file.write(b'{"before": "teh", "aft\n')  # cut off by a crash
        file.write(b"[1, 2]\n")  # JSON, but not a fix
        file.write(b'{"before": 5, "after": null}\n')
        file.write(b'{"before": "a", "after": "b", "context": "' + "说".encode()[:2] + b"\n")  # half a character
    history.record([{"before": "recieve", "after": "receive", "category": "spelling"}], path)
    assert [e["before"] for e in history.load(path)] == ["untill", "untill", "recieve"]
    change = Change(id=0, before="untill", after="until")
    history.mark_seen([change], path)
    assert change.seen == 2
    assert history.insights(path)["total"] == 3
    assert history.load(tmp_path / "missing.jsonl") == []
