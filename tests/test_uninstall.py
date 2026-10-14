import json
import subprocess

import pytest

from penwise import cli, keychain, setup_mac, uninstall


@pytest.fixture
def mac(tmp_path, monkeypatch):
    """A home folder with Penwise installed: hotkey, settings, history, logs, a key, Hammerspoon."""
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PENWISE_CONFIG", str(home / ".config" / "penwise" / "config.toml"))
    monkeypatch.setenv("PENWISE_HISTORY", str(home / ".local" / "share" / "penwise" / "history.jsonl"))
    monkeypatch.setattr(setup_mac, "hammerspoon_dir", lambda: home / ".hammerspoon")
    monkeypatch.setattr(setup_mac, "APP_PATHS", (home / "Applications" / "Hammerspoon.app",))
    monkeypatch.setattr(setup_mac, "HOTKEY_LOG", home / "Library" / "Logs" / "penwise-hotkey.log")
    for path in [
        home / ".config" / "penwise" / "config.toml",
        home / ".config" / "penwise" / "Try Penwise.txt",
        home / ".local" / "share" / "penwise" / "history.jsonl",
        home / "Library" / "Logs" / "penwise-hotkey.log",
        home / "Applications" / "Hammerspoon.app" / "Contents" / "Info.plist",
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x")
    setup_mac.install_spoon()
    setup_mac.write_snippet(home / ".hammerspoon" / "init.lua", background=True)
    keys = ["sk-or-v1-abc"]
    monkeypatch.setattr(keychain, "available", lambda: True)
    monkeypatch.setattr(keychain, "read", lambda: keys[0] if keys else "")
    monkeypatch.setattr(keychain, "delete", keys.clear)
    return home


def test_everything_penwise_put_there_goes(mac):
    removed = uninstall.run()
    assert removed == ["the hotkey", "your settings and history", "the API key in your Keychain"]
    assert not (mac / ".hammerspoon" / "Spoons" / "Penwise.spoon").exists()
    assert (mac / ".hammerspoon" / "init.lua").read_text() == ""
    assert not (mac / ".config" / "penwise").exists()  # its folder, once empty
    assert not (mac / ".local" / "share" / "penwise").exists()
    assert not (mac / "Library" / "Logs" / "penwise-hotkey.log").exists()
    assert keychain.read() == ""
    assert (mac / "Applications" / "Hammerspoon.app").exists()  # not asked to remove it
    assert uninstall.run() == []  # nothing left


def test_your_own_hammerspoon_setup_and_files_stay(mac):
    init_file = mac / ".hammerspoon" / "init.lua"
    init_file.write_text("hs.hotkey.bind({'cmd'}, 'h', hs.reload)\n\n" + init_file.read_text() + "\n-- mine\n")
    (mac / ".config" / "penwise" / "notes.txt").write_text("my own file")
    uninstall.run()
    assert init_file.read_text() == "hs.hotkey.bind({'cmd'}, 'h', hs.reload)\n\n-- mine\n"
    assert (mac / ".config" / "penwise" / "notes.txt").exists()


def test_hammerspoon_installed_for_penwise_goes_to_the_trash(mac):
    removed = uninstall.run(remove_hammerspoon=True)
    assert "Hammerspoon (in the Trash)" in removed
    assert (mac / ".Trash" / "Hammerspoon.app" / "Contents").exists()
    assert not (mac / "Applications" / "Hammerspoon.app").exists()
    assert not (mac / ".hammerspoon").exists()  # it held only Penwise


def test_files_of_your_own_in_hammerspoons_folder_stay(mac):
    (mac / ".hammerspoon" / "Spoons" / "Caffeine.spoon").mkdir()
    uninstall.run(remove_hammerspoon=True)
    assert (mac / ".hammerspoon" / "Spoons" / "Caffeine.spoon").exists()


def test_penwise_itself_is_uninstalled_with_uv(mac, monkeypatch):
    commands = []
    uv = mac / ".local" / "bin" / "uv"
    uv.parent.mkdir(parents=True)
    uv.write_text("")
    monkeypatch.setattr(uninstall.sys, "prefix", str(mac / ".local" / "share" / "uv" / "tools" / "penwise"))
    monkeypatch.setattr(uninstall.shutil, "which", lambda name: None)

    def run(command, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(uninstall.subprocess, "run", run)
    assert uninstall.run()[-1] == "Penwise"
    assert commands == [[str(uv), "tool", "uninstall", "penwise"]]


def test_the_command_asks_first_then_says_what_it_removed(mac, monkeypatch, capsys):
    quit_hammerspoon = []
    monkeypatch.setattr(uninstall, "quit_hammerspoon", lambda: quit_hammerspoon.append(True))
    monkeypatch.setattr("builtins.input", lambda prompt: "")  # Return: the answer is no
    assert cli.main(["uninstall"]) == 1
    assert "Nothing was removed." in capsys.readouterr().out
    assert (mac / ".config" / "penwise" / "config.toml").exists()

    assert cli.main(["uninstall", "--yes", "--hammerspoon", "--json"]) == 0
    assert "the hotkey" in json.loads(capsys.readouterr().out)["removed"]
    assert quit_hammerspoon == [True]  # last
