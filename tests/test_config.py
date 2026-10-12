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
