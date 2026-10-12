import pytest

from penwise import keychain
from penwise.config import ConfigError

# A stand-in for macOS's `security` tool: `-i` reads one command from stdin,
# `find-generic-password` prints the stored key. It logs its arguments.
FAKE_SECURITY = """#!/bin/sh
echo "$@" >> "{log}"
if [ "$1" = "-i" ]; then
  [ -e "{no_interactive}" ] && exit 0
  read -r line
  printf '%s' "$line" | sed -n 's/.*-w "\\(.*\\)"$/\\1/p' | tr -d '\\n' > "{store}"
elif [ "$1" = "add-generic-password" ]; then
  eval "last=\\${{$#}}"
  printf '%s' "$last" > "{store}"
elif [ "$1" = "find-generic-password" ]; then
  cat "{store}" 2>/dev/null || exit 44
fi
"""


@pytest.fixture
def security(tmp_path, monkeypatch):
    log, store = tmp_path / "log", tmp_path / "store"
    script = tmp_path / "bin" / "security"
    script.parent.mkdir()
    script.write_text(FAKE_SECURITY.format(log=log, store=store, no_interactive=tmp_path / "no-interactive"))
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{script.parent}:/usr/bin:/bin")
    monkeypatch.setattr(keychain.platform, "system", lambda: "Darwin")
    return log


def test_save_and_read(security):
    assert keychain.available()
    assert keychain.read() == ""
    keychain.save("sk-or-v1-abc123")
    assert keychain.read() == "sk-or-v1-abc123"


def test_the_key_is_never_a_command_line_argument(security):
    keychain.save("sk-or-v1-abc123")
    assert "sk-or-v1-abc123" not in security.read_text()


@pytest.mark.parametrize("key", ["", "two words", 'quote"d', "line\nbreak"])
def test_malformed_keys_are_refused(security, key):
    with pytest.raises(ConfigError, match="doesn't look like an API key"):
        keychain.save(key)


def test_falls_back_when_interactive_mode_does_not_save(security, tmp_path):
    (tmp_path / "no-interactive").touch()
    keychain.save("sk-or-v1-abc123")
    assert keychain.read() == "sk-or-v1-abc123"
