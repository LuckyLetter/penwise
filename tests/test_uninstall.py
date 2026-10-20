import json
import plistlib
import subprocess
from pathlib import Path

import pytest

from penwise import cli, keychain, setup_mac, uninstall


class Home(type(Path())):
    """The home folder, which also notes what runs once Hammerspoon has quit, and the Dock."""

    later: list
    dock: list


@pytest.fixture
def mac(tmp_path, monkeypatch):
    """A home folder with Penwise installed: hotkey, settings, history, logs, a key, Hammerspoon."""
    home = Home(tmp_path / "home")
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

    def trash(path):  # the Trash, as macOS's own call moves things there
        (home / ".Trash").mkdir(exist_ok=True)
        path.rename(home / ".Trash" / path.name)
        return True

    monkeypatch.setattr(uninstall, "trash", trash)
    later = []  # what runs once Hammerspoon has quit
    monkeypatch.setattr(uninstall, "_run_later", later.append)
    monkeypatch.setattr(uninstall, "quit_hammerspoon", lambda: later.append("quit Hammerspoon"))
    monkeypatch.setattr(uninstall, "forget_penwise_in_hammerspoon", lambda: later.append("forget Penwise's settings"))
    home.later = later
    home.dock = []  # this Mac's Dock stays as it is
    monkeypatch.setattr(uninstall, "forget_in_dock", lambda: home.dock.append("forget Penwise in the Dock"))
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


def test_hammerspoon_goes_to_the_trash_the_way_apps_do_it(tmp_path, monkeypatch):
    commands = []
    monkeypatch.setattr(uninstall.subprocess, "run", lambda command, **kw: commands.append(command))
    app = tmp_path / "Hammerspoon.app"
    app.mkdir()
    assert uninstall.trash(app) is False  # nothing really moved it here
    (command,) = commands
    assert command[:4] == ["osascript", "-l", "JavaScript", "-e"]  # not Finder: no permission to ask for
    assert "trashItemAtURL" in command[4] and f'"{app}"' in command[4]


def test_if_hammerspoon_cant_go_to_the_trash_it_says_so(mac, monkeypatch, capsys):
    monkeypatch.setattr(uninstall, "trash", lambda path: False)
    monkeypatch.setattr(uninstall, "quit_hammerspoon", lambda: None)
    assert cli.main(["uninstall", "--yes", "--hammerspoon"]) == 0
    out = capsys.readouterr().out
    assert "Hammerspoon is still in Applications" in out
    assert (mac / "Applications" / "Hammerspoon.app").exists()


def test_penwise_app_goes_to_the_trash_with_its_folder(mac, monkeypatch, capsys):
    app = mac / "Applications" / "Penwise.app"
    (app / "Contents").mkdir(parents=True)
    support = mac / "Library" / "Application Support" / "Penwise"
    (support / "Hammerspoon.app").mkdir(parents=True)
    (support / "site").mkdir()
    monkeypatch.setenv("PENWISE_APP", str(app))
    monkeypatch.setattr(setup_mac, "SUPPORT", support)
    monkeypatch.setattr(setup_mac, "APP_PATHS", (mac / "Nowhere" / "Hammerspoon.app", support / "Hammerspoon.app"))
    quit = []
    monkeypatch.setattr(uninstall, "quit_hammerspoon", lambda: quit.append(True))
    assert cli.main(["uninstall", "--yes"]) == 0
    assert not app.exists() and (mac / ".Trash" / "Penwise.app").exists()
    assert not support.exists()  # its copy of Hammerspoon and its updates
    assert quit == [True]  # that Hammerspoon was Penwise's own: it stops too
    assert mac.dock == ["forget Penwise in the Dock"]  # and its place in the Dock goes
    assert "Penwise" in capsys.readouterr().out


def test_everything_penwise_set_up_goes_hammerspoon_and_its_files_too(mac):
    assert cli.main(["uninstall", "--yes", "--hammerspoon"]) == 0
    assert (mac / ".Trash" / "Hammerspoon.app").exists()
    script, quit = mac.later
    assert quit == "quit Hammerspoon"  # then, on its own, once Hammerspoon has quit:
    assert "defaults delete org.hammerspoon.Hammerspoon" in script  # its preferences
    assert f"rm -rf {mac}/Library/WebKit/org.hammerspoon.Hammerspoon" in script  # its web data
    assert "tccutil reset Accessibility org.hammerspoon.Hammerspoon" in script  # its permission
    assert "osascript" not in script  # and nothing more to say: you asked for it


def test_your_own_hammerspoon_keeps_everything_but_penwises_settings(mac):
    assert cli.main(["uninstall", "--yes"]) == 0
    assert mac.later == ["forget Penwise's settings"]


def tile(path, bundle=""):
    """A Dock tile, as the Dock keeps it."""
    data = {"file-data": {"_CFURLString": f"file://{path}/", "_CFURLStringType": 15}, "file-label": Path(path).stem}
    return {"tile-data": {**data, **({"bundle-identifier": bundle} if bundle else {})}, "tile-type": "file-tile"}


@pytest.fixture
def dock(tmp_path, monkeypatch):
    """The Dock's settings, read and written through `defaults`, and a Dock that can restart."""
    prefs = tmp_path / "com.apple.dock.plist"
    log = tmp_path / "log"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    defaults = f'if [ "$1" = export ]; then cat "{prefs}"; else cat > "{prefs}"; echo "defaults $*" >> "{log}"; fi'
    (bin_dir / "defaults").write_text(f"#!/bin/sh\n{defaults}\n")
    (bin_dir / "killall").write_text(f'#!/bin/sh\necho "killall $*" >> "{log}"\n')
    for tool in bin_dir.iterdir():
        tool.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:/usr/bin:/bin")
    return prefs, log


def test_penwise_leaves_the_dock_with_the_app(dock):
    prefs, log = dock
    notes = tile("/System/Applications/Notes.app", "com.apple.Notes")
    prefs.write_bytes(
        plistlib.dumps(
            {
                "persistent-apps": [notes, tile("/Applications/Penwise.app", uninstall.APP_ID)],  # kept in the Dock
                "recent-apps": [tile("/Users/me/Applications/Penwise.app")],  # or opened lately
                "tilesize": 48,
            }
        )
    )
    assert uninstall.forget_in_dock() is True
    after = plistlib.loads(prefs.read_bytes())
    assert after == {"persistent-apps": [notes], "recent-apps": [], "tilesize": 48}  # the rest as it was
    assert log.read_text().splitlines() == ["defaults import com.apple.dock -", "killall Dock"]  # it reads them again


def test_a_dock_without_penwise_is_left_alone(dock):
    prefs, log = dock
    prefs.write_bytes(plistlib.dumps({"persistent-apps": [tile("/Applications/Safari.app", "com.apple.Safari")]}))
    assert uninstall.forget_in_dock() is False
    assert not log.exists()  # not even restarted


def test_quitting_hammerspoon_ends_the_launchd_job_penwise_started_it_with(monkeypatch):
    commands = []
    monkeypatch.setattr(uninstall.subprocess, "run", lambda command, **kwargs: commands.append(command))
    uninstall.quit_hammerspoon()
    job = f"gui/{uninstall.os.getuid()}/{setup_mac.LAUNCHD_LABEL}"
    assert commands == [["launchctl", "bootout", job], ["pkill", "-x", "Hammerspoon"]]
