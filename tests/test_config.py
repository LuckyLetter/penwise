import sys

import pytest

from penwise import config
from penwise.config import Config, ConfigError


def test_missing_file_gives_local_defaults(tmp_path):
    cfg = config.load(tmp_path / "missing.toml")
    assert cfg.base_url == "http://localhost:11434/v1"
    assert cfg.model == "gemma3:1b"
    assert cfg.explain is False


def test_template_is_valid_and_matches_defaults(tmp_path):
    path = config.write_template(tmp_path / "config.toml")
    assert config.load(path) == Config()


def test_template_is_not_overwritten_by_accident(tmp_path):
    path = config.write_template(tmp_path / "config.toml")
    with pytest.raises(ConfigError, match="already exists"):
        config.write_template(path)
    config.write_template(path, force=True)


@pytest.mark.parametrize(
    "content, message",
    [
        ('modle = "x"', "Unknown setting"),
        ("explain = 1", "true or false"),
        ('timeout = "60"', "number"),
        ('mode = "rewrite"', "mode should be"),
        ("model = ", "Could not read"),
    ],
)
def test_bad_settings_are_reported(tmp_path, content, message):
    path = tmp_path / "config.toml"
    path.write_text(content)
    with pytest.raises(ConfigError, match=message):
        config.load(path)


def test_api_key_sources(monkeypatch):
    monkeypatch.delenv("PENWISE_API_KEY", raising=False)
    assert Config().resolve_api_key() == ""
    assert Config(api_key="direct").resolve_api_key() == "direct"

    monkeypatch.setenv("MY_KEY", "from-env")
    assert Config(api_key_env="MY_KEY").resolve_api_key() == "from-env"

    command = f'"{sys.executable}" -c "print(\'from-command\')"'
    assert Config(api_key_command=command).resolve_api_key() == "from-command"


def test_failing_key_command_is_reported():
    with pytest.raises(ConfigError, match="did not print a key"):
        Config(api_key_command=f'"{sys.executable}" -c "raise SystemExit(1)"').resolve_api_key()


def test_set_values_keeps_comments_and_other_settings(tmp_path):
    path = config.write_template(tmp_path / "config.toml")
    config.set_values({"model": "mistralai/mistral-small-2603", "reasoning_effort": "low"}, path)
    text = path.read_text()
    assert "# Penwise settings." in text
    assert 'model = "mistralai/mistral-small-2603"' in text
    assert config.load(path).reasoning_effort == "low"
    config.set_values({"reasoning_effort": None}, path)
    assert config.load(path).reasoning_effort == ""


def test_set_values_never_writes_a_broken_file(tmp_path):
    path = tmp_path / "config.toml"
    with pytest.raises(ConfigError):
        config.set_values({"mode": "rewrite"}, path)
    assert not path.exists()


def test_write_config_keeps_a_key_private(tmp_path):
    path = config.write_config({"model": "m", "api_key": "secret"}, tmp_path / "config.toml")
    assert config.load(path).api_key == "secret"
    assert path.stat().st_mode & 0o077 == 0


@pytest.mark.parametrize(
    "name, raw, value",
    [("explain", "on", True), ("timeout", "30", 30), ("temperature", "0.1", 0.1), ("model", "x", "x")],
)
def test_parse_value(name, raw, value):
    assert config.parse_value(name, raw) == value


def test_a_key_missing_from_the_keychain_is_explained_in_plain_words():
    cfg = Config(api_key_command="security find-generic-password -s penwise-test-missing -w")
    with pytest.raises(ConfigError, match="couldn't read your API key from the Keychain"):
        cfg.resolve_api_key()
