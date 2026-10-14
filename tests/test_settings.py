import dataclasses
import io
import json
import stat
from pathlib import Path

import pytest

from penwise import cli, config, keychain, ollama, presets, settings


def test_a_fresh_install_is_not_configured(isolated):
    data = settings.describe()
    assert data["configured"] is False
    assert data["provider"] == "ollama"  # the default: a model on this Mac
    openrouter = next(p for p in data["providers"] if p["key"] == "openrouter")
    assert openrouter["key_url"] and openrouter["models"][0]["id"] == "mistralai/mistral-small-2603"


def test_saving_tests_the_model(isolated, server):
    result = settings.save({"provider": "custom", "base_url": server.url, "model": "some-model"})
    assert result == {
        "saved": True,
        "ok": True,
        "before": "This sentence have a error.",
        "after": "This sentence has an error.",
        "seconds": result["seconds"],
    }
    cfg = config.load()
    assert (cfg.base_url, cfg.model, cfg.explain) == (server.url, "some-model", False)  # on this computer
    assert settings.describe()["configured"] is True


def test_a_key_goes_to_the_keychain_when_there_is_one(isolated, server, monkeypatch):
    saved = []
    monkeypatch.setattr(keychain, "available", lambda: True)
    monkeypatch.setattr(keychain, "save", saved.append)
    settings.save({"provider": "custom", "base_url": server.url, "model": "m", "key": "secret"})
    assert saved == ["secret"]
    assert config.load().api_key_command == keychain.READ_COMMAND
    assert settings.describe()["has_key"] is True


def test_without_a_keychain_the_key_is_readable_only_by_you(isolated, server, monkeypatch):
    monkeypatch.setattr(keychain, "available", lambda: False)
    settings.save({"provider": "custom", "base_url": server.url, "model": "m", "key": "secret"})
    assert config.load().api_key == "secret"
    assert stat.S_IMODE(config.config_path().stat().st_mode) == 0o600


def test_what_is_missing_is_said_and_nothing_saved(isolated):
    assert settings.save({"provider": "openrouter", "model": "m"})["message"] == "Paste your API key."
    # An API address Penwise knows gets that service's checks.
    openrouter = {"provider": "custom", "base_url": "https://openrouter.ai/api/v1/", "model": "m"}
    assert settings.save(openrouter)["message"] == "Paste your API key."
    bad_key = settings.save({"provider": "openrouter", "model": "m", "key": "my-password"})
    assert "starts with sk-or-" in bad_key["message"]
    assert settings.save({"provider": "custom", "model": "m"})["message"].startswith("Enter the service's address")
    assert settings.save({"provider": "ollama", "model": ""})["message"] == "Choose a model."
    assert not config.config_path().exists()


def test_settings_that_dont_work_are_saved_and_the_problem_shown(isolated):
    result = settings.save({"provider": "custom", "base_url": "http://127.0.0.1:9/v1", "model": "m"})
    assert result["saved"] is True and result["ok"] is False
    assert "Could not reach" in result["message"]


def test_the_command_reads_settings_from_the_environment(isolated, server, monkeypatch, capsys):
    request = {"provider": "custom", "base_url": server.url, "model": "m"}
    monkeypatch.setenv("PENWISE_SETTINGS", json.dumps(request))
    assert cli.main(["settings", "--save"]) == 0
    assert json.loads(capsys.readouterr().out)["after"] == "This sentence has an error."
    assert cli.main(["settings"]) == 0
    assert json.loads(capsys.readouterr().out)["model"] == "m"


@pytest.fixture
def on_this_mac(server, monkeypatch):
    """Ollama on this Mac, answering at the fake server; what it has and does is set per test."""
    local = dataclasses.replace(presets.OLLAMA, base_url=server.url)
    monkeypatch.setattr(presets, "OLLAMA", local)
    monkeypatch.setattr(presets, "PROVIDERS", (presets.OPENROUTER, local, presets.CUSTOM))
    monkeypatch.setattr(ollama, "running", lambda: True)
    monkeypatch.setattr(ollama, "models", lambda: {"gemma3:1b"})
    return monkeypatch


def test_without_ollama_the_window_links_to_it(isolated, on_this_mac):
    on_this_mac.setattr(ollama, "running", lambda: False)
    on_this_mac.setattr(ollama, "app", lambda: None)
    result = settings.save({"provider": "ollama", "model": "gemma3:1b"})
    assert result["saved"] is True and result["ok"] is False
    assert result["message"].startswith("Models on your Mac run in Ollama, a free app.")
    assert result["link"] == {"label": "Download Ollama", "url": "https://ollama.com/download"}


def test_ollama_is_started_and_the_model_downloaded_without_the_terminal(isolated, on_this_mac):
    state = {"running": False}
    on_this_mac.setattr(ollama, "running", lambda: state["running"])
    on_this_mac.setattr(ollama, "app", lambda: Path("/Applications/Ollama.app"))
    on_this_mac.setattr(ollama, "start", lambda: state.update(running=True) or True)
    on_this_mac.setattr(ollama, "models", lambda: set())
    size = 815_000_000
    on_this_mac.setattr(ollama, "pull", lambda model: iter([(0, size), (1, size), (size, size)]))
    steps = []
    result = settings.save({"provider": "ollama", "model": "gemma3:1b"}, steps.append)
    assert steps == [
        "Starting Ollama…",
        "Downloading gemma3:1b…",
        "Downloading gemma3:1b… 0% of 815 MB",  # once per percent
        "Downloading gemma3:1b… 100% of 815 MB",
        "Testing the model…",
    ]
    assert result["ok"] is True and result["after"] == "This sentence has an error."


def test_a_model_ollama_doesnt_have_is_named(isolated, on_this_mac):
    on_this_mac.setattr(ollama, "models", lambda: set())

    def pull(model):
        raise ollama.OllamaError(f"Ollama has no model called “{model}”. Check its name at ollama.com/library.")
        yield

    on_this_mac.setattr(ollama, "pull", pull)
    result = settings.save({"provider": "ollama", "model": "gemma9:1b"})
    assert result["ok"] is False and "no model called “gemma9:1b”" in result["message"]


def test_the_command_says_what_takes_a_while_then_the_result(isolated, on_this_mac, monkeypatch, capsys):
    on_this_mac.setattr(ollama, "models", lambda: set())
    on_this_mac.setattr(ollama, "pull", lambda model: iter([(5_000_000, 10_000_000), (10, 10)]))
    monkeypatch.setenv("PENWISE_SETTINGS", json.dumps({"provider": "ollama", "model": "gemma3:1b"}))
    assert cli.main(["settings", "--save"]) == 0
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert lines[:3] == [
        {"type": "progress", "text": "Downloading gemma3:1b…"},
        {"type": "progress", "text": "Downloading gemma3:1b… 50% of 10 MB"},
        {"type": "progress", "text": "Testing the model…"},  # nothing for the small part
    ]
    assert lines[-1]["ok"] is True


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_ollama_downloads_report_their_progress(monkeypatch):
    lines = [
        {"status": "pulling manifest"},
        {"status": "pulling 7cd4", "total": 100, "completed": 40},
        {"status": "success"},
    ]
    body = b"".join(json.dumps(line).encode() + b"\n" for line in lines)
    monkeypatch.setattr(ollama.urllib.request, "urlopen", lambda request, timeout: Response(body))
    assert list(ollama.pull("gemma3:1b")) == [(40, 100)]

    missing = json.dumps({"error": "pull model manifest: file does not exist"}).encode()
    monkeypatch.setattr(ollama.urllib.request, "urlopen", lambda request, timeout: Response(missing))
    with pytest.raises(ollama.OllamaError, match="no model called “gemma9:1b”"):
        list(ollama.pull("gemma9:1b"))


def test_a_model_without_a_tag_is_its_latest_version():
    assert ollama.has_model("llama3.2", {"llama3.2:latest"})
    assert not ollama.has_model("llama3.2:1b", {"llama3.2:latest"})
