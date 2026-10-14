import json
import stat

from penwise import cli, config, keychain, settings


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
