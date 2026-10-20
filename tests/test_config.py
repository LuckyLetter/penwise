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
        ('modle = "x"', "modle is not a Penwise setting"),
        ("explain = 1", "explain should be true or false"),
        ('timeout = "60"', "timeout should be a number"),
        ('mode = "rewrite"', "mode should be one of fix, improve"),
    ],
)
def test_a_setting_that_cant_be_used_is_reported_and_its_default_used(tmp_path, content, message):
    path = tmp_path / "config.toml"
    path.write_text(f'model = "mine"\n{content}\n')
    cfg = config.load(path)  # one bad line never stops every check
    assert [problem for _, problem in cfg.problems] == [message]
    assert cfg.model == "mine" and cfg.mode == "fix" and cfg.timeout == 60 and cfg.explain is False


def test_an_unreadable_file_is_reported(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("model = ")
    with pytest.raises(ConfigError, match=r"couldn't read its settings \(a mistake in .*config\.toml\)\. Open the"):
        config.load(path)
    path.write_text("explain = tru\n")
    with pytest.raises(ConfigError, match=r"\(a mistake in .*config\.toml, at line 1, column \d+\)\. Open the"):
        config.load(path)


def test_saving_repairs_a_damaged_file(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('mode = "shout"\nexplain = tru\nfuture_setting = 1\nmodel = "old"\n')
    config.set_values({"model": "new"}, path)  # what the settings window does
    cfg = config.load(path)
    assert cfg.model == "new" and cfg.explain is False
    assert "# Penwise couldn't read this line: explain = tru" in path.read_text()
    with pytest.raises(ConfigError, match="mode should be one of"):
        config.set_values({"mode": "shout"}, path)  # but a value you set yourself must work


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
    config.set_values({"model": "mistralai/mistral-small-2603", "language": "ja"}, path)
    text = path.read_text()
    assert "# Penwise settings." in text
    assert 'model = "mistralai/mistral-small-2603"' in text
    assert config.load(path).language == "ja"
    config.set_values({"language": None}, path)
    assert config.load(path).language == "en"


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
