import io
import json

import pytest

from penwise import cli, history


def run(args, monkeypatch, capsys, stdin=""):
    monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
    code = cli.main(args)
    out, err = capsys.readouterr()
    return code, out, err


def test_check_text_format_prints_only_the_edit(server, isolated, monkeypatch, capsys):
    code, out, _ = run(
        ["check", "--base-url", server.url, "-f", "text"], monkeypatch, capsys, stdin="This have a error.\n"
    )
    assert code == 0
    assert out == "This has an error.\n"


def test_text_after_double_dash_is_kept_exactly(server, isolated, monkeypatch, capsys):
    text = "-starts with a dash\nand have a error  "
    code, out, _ = run(["check", "--base-url", server.url, "-f", "text", "--", text], monkeypatch, capsys)
    assert code == 0
    assert out == "-starts with a dash\nand has an error  "


def test_check_jsonl_streams_events(server, isolated, monkeypatch, capsys):
    code, out, _ = run(
        ["check", "This have a error.", "--base-url", server.url, "-f", "jsonl", "--explain"], monkeypatch, capsys
    )
    events = [json.loads(line) for line in out.splitlines()]
    assert code == 0
    assert [e["type"] for e in events] == ["start", "result", "explanations", "done"]
    assert events[1]["edited"] == "This has an error."
    assert events[2]["reasons"] == {"0": "Reason 1.", "1": "Reason 2."}


def test_check_pretty_lists_changes(server, isolated, monkeypatch, capsys):
    code, out, _ = run(
        ["check", "The informations is here.", "--base-url", server.url, "-f", "pretty"], monkeypatch, capsys
    )
    assert code == 0
    assert "Uncountable noun" in out
    assert "{+information+}" in out


def test_check_shows_how_often_a_fix_was_made(server, isolated, monkeypatch, capsys):
    history.record([{"before": "untill", "after": "until", "category": "spelling"}] * 2)
    _, out, _ = run(["check", "Wait untill noon.", "--base-url", server.url, "-f", "json"], monkeypatch, capsys)
    assert json.loads(out)["changes"][0]["seen"] == 2


def test_errors_are_reported_in_jsonl_and_stderr(isolated, monkeypatch, capsys):
    code, out, err = run(["check", "Hi.", "--base-url", "http://127.0.0.1:9/v1", "-f", "jsonl"], monkeypatch, capsys)
    assert code == 1
    assert json.loads(out.splitlines()[-1])["type"] == "error"
    assert err.startswith("penwise: Could not reach")


def test_empty_input_is_an_error(isolated, monkeypatch, capsys):
    code, _, err = run(["check", "-f", "text"], monkeypatch, capsys, stdin="   ")
    assert code == 1
    assert "Nothing to check" in err


def test_record_respects_the_history_setting(isolated, monkeypatch, capsys):
    payload = json.dumps({"changes": [{"before": "a", "after": "an", "category": "article"}]})
    run(["record"], monkeypatch, capsys, stdin=payload)
    assert len(history.load()) == 1

    (isolated / "config.toml").write_text("history = false\n")
    run(["record"], monkeypatch, capsys, stdin=payload)
    assert len(history.load()) == 1


def test_init_then_insights(isolated, monkeypatch, capsys):
    code, out, _ = run(["init"], monkeypatch, capsys)
    assert code == 0 and (isolated / "config.toml").exists()

    _, out, _ = run(["insights"], monkeypatch, capsys)
    assert "No history yet" in out

    history.record([{"before": "in", "after": "on", "category": "preposition"}] * 2)
    _, out, _ = run(["insights"], monkeypatch, capsys)
    assert "Prepositions" in out and "in → on" in out


@pytest.mark.parametrize("args", [["--help"], ["check", "--help"]])
def test_help(args, monkeypatch, capsys):
    with pytest.raises(SystemExit) as exit_info:
        run(args, monkeypatch, capsys)
    assert exit_info.value.code == 0
