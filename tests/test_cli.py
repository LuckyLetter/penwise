import io
import json

import pytest

from penwise import cli, config, history


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


def test_model_switch_is_tested_and_saved(server, isolated, monkeypatch, capsys):
    config.set_values({"base_url": server.url, "model": "old-model"})
    code, out, _ = run(["model", "openai/gpt-6-luna"], monkeypatch, capsys)
    assert code == 0 and "Now using openai/gpt-6-luna" in out
    cfg = config.load()
    assert (cfg.model, cfg.reasoning_effort) == ("openai/gpt-6-luna", "none")
    assert server.requests[-1]["model"] == "openai/gpt-6-luna"

    run(["model", "mistralai/mistral-small-2603"], monkeypatch, capsys)
    assert config.load().reasoning_effort == ""  # Mistral Small doesn't think by default


def test_a_model_that_fails_the_test_is_not_saved(server, isolated, monkeypatch, capsys):
    config.set_values({"base_url": server.url, "model": "old-model"})
    server.status = 404
    code, out, _ = run(["model", "no/such-model"], monkeypatch, capsys)
    assert code == 1 and "Still using old-model" in out
    assert config.load().model == "old-model"


def test_model_without_an_id_lists_suggestions(isolated, monkeypatch, capsys):
    config.set_values({"base_url": "https://openrouter.ai/api/v1", "model": "x"})
    _, out, _ = run(["model"], monkeypatch, capsys)
    assert "mistralai/mistral-small-2603" in out


def test_config_set_show_and_unset(isolated, monkeypatch, capsys):
    run(["config", "set", "timeout", "30"], monkeypatch, capsys)
    run(["config", "set", "explain", "yes"], monkeypatch, capsys)
    assert (config.load().timeout, config.load().explain) == (30, True)
    _, out, _ = run(["config"], monkeypatch, capsys)
    assert "timeout           30" in out and "explain           true" in out
    run(["config", "unset", "timeout"], monkeypatch, capsys)
    assert config.load().timeout == 60


def test_config_rejects_bad_input(isolated, monkeypatch, capsys):
    code, _, err = run(["config", "set", "explain", "maybe"], monkeypatch, capsys)
    assert code == 1 and "true or false" in err
    code, _, err = run(["config", "set", "modle", "x"], monkeypatch, capsys)
    assert code == 1 and "Unknown setting" in err


def test_first_run_points_to_setup(isolated, monkeypatch, capsys):
    class Terminal(io.StringIO):
        def isatty(self):
            return True

    monkeypatch.setattr("sys.stdin", Terminal())
    assert cli.main([]) == 0
    assert "Run `penwise setup` to get started" in capsys.readouterr().out


def test_keep_words(server, isolated, monkeypatch, capsys):
    _, out, _ = run(["keep"], monkeypatch, capsys)
    assert "No words kept yet" in out
    run(["keep", "Pytorch", "ResNet"], monkeypatch, capsys)
    run(["keep", "Pytorch"], monkeypatch, capsys)  # no duplicates
    assert config.load().keep == ["Pytorch", "ResNet"]
    run(["keep", "--remove", "ResNet"], monkeypatch, capsys)
    assert config.load().keep == ["Pytorch"]
    server.reply = lambda body: "We use PyTorch."
    _, out, _ = run(["check", "We use Pytorch.", "--base-url", server.url, "-f", "text"], monkeypatch, capsys)
    assert out == "We use Pytorch."


def test_update_check(isolated, monkeypatch, capsys):
    monkeypatch.setattr(cli.updater, "check", lambda: "2 new changes")
    _, out, _ = run(["update", "--check", "--json"], monkeypatch, capsys)
    assert json.loads(out) == {"available": True, "detail": "2 new changes"}
    monkeypatch.setattr(cli.updater, "check", lambda: None)
    _, out, _ = run(["update", "--check"], monkeypatch, capsys)
    assert "up to date" in out


def test_insights_as_json(isolated, monkeypatch, capsys):
    history.record([{"before": "in", "after": "on", "category": "preposition", "context_before": "results "}] * 2)
    _, out, _ = run(["insights", "--json"], monkeypatch, capsys)
    data = json.loads(out)
    assert data["total"] == 2
    assert data["categories"][0]["label"] == "Prepositions"
    assert "learn them in phrases" in data["categories"][0]["note"]
    assert data["repeated"][0]["pair"] == "in → on"
