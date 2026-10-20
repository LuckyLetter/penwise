import dataclasses
import io
import json
import plistlib
from pathlib import Path

import pytest

from penwise import cli, config, history, ollama, presets, setup_mac


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


def test_check_starts_ollama_when_it_was_quit(server, isolated, monkeypatch, capsys):
    started = []
    monkeypatch.setattr(ollama, "serves", lambda base_url: True)  # the fake server stands in for Ollama
    monkeypatch.setattr(ollama, "running", lambda: bool(started))
    monkeypatch.setattr(ollama, "app", lambda: Path("/Applications/Ollama.app"))
    monkeypatch.setattr(ollama, "start", lambda: started.append(True) or True)
    code, out, _ = run(["check", "This have a error.", "--base-url", server.url, "-f", "jsonl"], monkeypatch, capsys)
    events = [json.loads(line) for line in out.splitlines()]
    assert code == 0 and started == [True]
    assert [e["type"] for e in events] == ["start", "status", "status", "result", "done"]
    assert [e["text"] for e in events[1:3]] == ["Starting Ollama…", ""]

    capsys.readouterr()
    run(["check", "This have a error.", "--base-url", server.url, "-f", "jsonl"], monkeypatch, capsys)
    assert started == [True]  # running: nothing to start


def test_only_ollama_on_this_mac_is_started():
    assert ollama.serves("http://localhost:11434/v1")
    assert ollama.serves("http://127.0.0.1:11434/v1/")
    assert not ollama.serves("http://localhost:1234/v1")  # LM Studio
    assert not ollama.serves("https://openrouter.ai/api/v1")
    assert not ollama.serves("http://localhost:11434x/v1")  # a typo


def test_ollama_starts_out_of_sight(monkeypatch):
    opened = []
    monkeypatch.setattr(ollama, "app", lambda: Path("/Applications/Ollama.app"))
    monkeypatch.setattr(ollama.subprocess, "run", lambda args, **kwargs: opened.append(args))
    monkeypatch.setattr(ollama, "running", lambda: bool(opened))
    assert ollama.start()
    assert opened == [["open", "-g", "-j", "/Applications/Ollama.app"]]  # your app stays in front


def test_check_my_setup_starts_with_the_versions(server, isolated, monkeypatch, capsys):
    (isolated / "config.toml").write_text(f'base_url = "{server.url}"\nmodel = "some-model"\n')
    monkeypatch.setattr("platform.system", lambda: "Darwin")
    monkeypatch.setattr("platform.mac_ver", lambda: ("26.0.1", ("", "", ""), "arm64"))
    monkeypatch.setattr("penwise.setup_mac.hammerspoon_installed", lambda: True)
    monkeypatch.setattr("penwise.setup_mac.spoon_installed", lambda: True)
    monkeypatch.setattr("penwise.setup_mac.hammerspoon_version", lambda: "1.0.0")
    monkeypatch.setattr("penwise.setup_mac.hotkey_log", lambda: [])
    code, out, _ = run(["doctor"], monkeypatch, capsys)
    lines = out.splitlines()
    assert code == 0
    assert lines[0] == f"✓ Penwise     {cli.__version__} on macOS 26.0.1"
    assert "✓ Hotkey      installed (Hammerspoon 1.0.0)" in lines


def test_the_hammerspoon_version_comes_from_its_app(tmp_path, monkeypatch):
    app = tmp_path / "Hammerspoon.app"
    monkeypatch.setattr(setup_mac, "APP_PATHS", (tmp_path / "missing.app", app))
    assert setup_mac.hammerspoon_version() == ""
    (app / "Contents").mkdir(parents=True)
    (app / "Contents" / "Info.plist").write_text("not a plist")
    assert setup_mac.hammerspoon_version() == ""
    (app / "Contents" / "Info.plist").write_bytes(plistlib.dumps({"CFBundleShortVersionString": "1.0.0"}))
    assert setup_mac.hammerspoon_version() == "1.0.0"


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
    error = json.loads(out.splitlines()[-1])
    assert error["type"] == "error" and error["in_settings"] is False  # on this Mac: nothing to change there
    assert err.startswith("penwise: Could not reach")


def test_in_the_terminal_an_error_fixed_in_the_settings_says_how_to_get_there(server, isolated, monkeypatch, capsys):
    server.status = 401
    code, _, err = run(["check", "Hi.", "--base-url", server.url], monkeypatch, capsys)
    assert code == 1
    first, second = err.splitlines()
    assert first.startswith("penwise: The service refused the API Key (401). Paste a new one in the settings.")
    assert second == "To change the settings, run `penwise setup`."


def test_empty_input_is_an_error(isolated, monkeypatch, capsys):
    code, _, err = run(["check", "-f", "text"], monkeypatch, capsys, stdin="   ")
    assert code == 1
    assert "Nothing to check" in err


def test_record_respects_the_history_setting(isolated, monkeypatch, capsys):
    payload = json.dumps({"changes": [{"before": "a", "after": "an", "category": "article"}]})
    run(["record"], monkeypatch, capsys, stdin=payload)
    assert len(history.load()) == 1

    run(["record", payload], monkeypatch, capsys)  # as an argument, the way the Mac panel sends it
    assert len(history.load()) == 2

    (isolated / "config.toml").write_text("history = false\n")
    run(["record"], monkeypatch, capsys, stdin=payload)
    assert len(history.load()) == 2


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
    # As Save does: what makes the model think less (here, as OpenRouter lists GPT-6 Luna), tried and kept.
    monkeypatch.setattr(cli.settings, "quicker_setting", lambda base_url, model: {"reasoning": {"effort": "none"}})
    code, out, _ = run(["model", "openai/gpt-6-luna"], monkeypatch, capsys)
    assert code == 0 and "Now using openai/gpt-6-luna" in out
    cfg = config.load()
    assert cfg.model == "openai/gpt-6-luna"
    assert cfg.less_thinking == {"model": cfg.model, "endpoint": server.url, "send": {"reasoning": {"effort": "none"}}}
    assert server.requests[-1]["model"] == "openai/gpt-6-luna"
    assert server.requests[-1]["reasoning"] == {"effort": "none"}

    def refused(body):  # a model that won't think less
        if "reasoning" in body:
            raise server.Reject(400, "reasoning is not supported")
        return server.default_reply(body)

    server.reply = refused
    run(["model", "other/model"], monkeypatch, capsys)
    assert config.load().less_thinking["send"] == {}  # remembered: no check asks it again


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


def test_config_shows_what_save_found(isolated, monkeypatch, capsys):
    found = {"model": "m", "endpoint": "https://x.test/v1", "send": {"enable_thinking": False}}
    config.set_values({"less_thinking": found})
    _, out, _ = run(["config"], monkeypatch, capsys)
    assert '"send": {"enable_thinking": false}' in out


def test_config_rejects_bad_input(isolated, monkeypatch, capsys):
    code, _, err = run(["config", "set", "explain", "maybe"], monkeypatch, capsys)
    assert code == 1 and "true or false" in err
    code, _, err = run(["config", "set", "modle", "x"], monkeypatch, capsys)
    assert code == 1 and "Unknown setting" in err
    code, _, err = run(["config", "set", "less_thinking", "x"], monkeypatch, capsys)
    assert code == 1 and "press Save" in err


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
    assert json.loads(out) == {"available": True, "detail": "2 new changes", "in_place": False}
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


def test_improve_takes_its_tone_from_the_app(server, isolated, monkeypatch, capsys):
    args = ["check", "Hi, can you check this?", "--base-url", server.url, "-f", "jsonl", "-m", "improve"]
    _, out, _ = run([*args, "--app", "com.apple.mail"], monkeypatch, capsys)
    assert json.loads(out.splitlines()[0])["style"] == "email"
    assert "The text is an email" in server.requests[-1]["messages"][0]["content"]
    _, out, _ = run([*args, "--style", "chat"], monkeypatch, capsys)
    assert json.loads(out.splitlines()[0])["style"] == "chat"


def test_tips_are_shown_to_new_users_only(server, isolated, monkeypatch, capsys):
    args = ["check", "This have a error.", "--base-url", server.url, "-f", "jsonl"]
    _, out, _ = run(args, monkeypatch, capsys)
    assert json.loads(out.splitlines()[0])["tips"] is True
    history.record([{"before": "a", "after": "an", "category": "article"}] * 3)
    _, out, _ = run(args, monkeypatch, capsys)
    assert json.loads(out.splitlines()[0])["tips"] is False


def test_try_opens_the_practice_note_on_a_mac(isolated, monkeypatch, capsys):
    monkeypatch.setattr(cli.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(cli.setup_mac.subprocess, "run", lambda command, **kwargs: None)
    _, out, _ = run(["try"], monkeypatch, capsys)
    assert "Try Penwise.txt" in out and (isolated / "Try Penwise.txt").exists()


def test_running_out_of_credits_comes_with_the_page_to_add_them(server, isolated, monkeypatch, capsys):
    service = dataclasses.replace(presets.OPENROUTER, base_url=server.url)
    monkeypatch.setattr(presets, "PROVIDERS", (service,))
    server.status = 402
    code, out, err = run(["check", "Hi.", "--base-url", server.url, "-f", "jsonl"], monkeypatch, capsys)
    assert code == 1
    assert json.loads(out.splitlines()[-1])["link"]["url"] == "https://openrouter.ai/settings/credits"
    assert err.splitlines()[-1] == "Add credits: https://openrouter.ai/settings/credits"
