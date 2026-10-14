import subprocess
from pathlib import Path

import pytest

from penwise import cli, setup_mac


def test_spoon_ships_with_the_package():
    source = setup_mac.spoon_source()
    assert (source / "init.lua").exists()
    assert (source / "panel.html").exists()


def test_install_spoon_replaces_an_old_copy(tmp_path):
    target = setup_mac.install_spoon(tmp_path)
    (target / "stale.txt").write_text("old")
    target = setup_mac.install_spoon(tmp_path)
    assert (target / "init.lua").exists()
    assert not (target / "stale.txt").exists()


def test_snippet_is_added_once(tmp_path):
    init_file = tmp_path / "init.lua"
    init_file.write_text("-- my own config\n")
    assert setup_mac.write_snippet(init_file) == "added"
    assert setup_mac.write_snippet(init_file) == "unchanged"
    text = init_file.read_text()
    assert text.startswith("-- my own config\n\n")
    assert text.count('hs.loadSpoon("Penwise")') == 1
    assert "quick = " in text


def test_refreshing_keeps_hotkeys_you_changed(tmp_path, monkeypatch):
    init_file = tmp_path / "init.lua"
    setup_mac.write_snippet(init_file)
    init_file.write_text(init_file.read_text().replace('"alt" }, "p"', '"alt" }, "e"'))
    monkeypatch.setattr(setup_mac, "penwise_command", lambda: ("/new/bin/penwise", []))
    assert setup_mac.write_snippet(init_file) == "updated"
    text = init_file.read_text()
    assert 'spoon.Penwise.bin = "/new/bin/penwise"' in text
    assert '"alt" }, "e"' in text


def test_the_block_from_version_0_1_is_upgraded(tmp_path):
    init_file = tmp_path / "init.lua"
    init_file.write_text(
        "-- before\n\n"
        "-- Penwise: select text anywhere, then press ⌃⌥P (fix) or ⌃⌥⇧P (improve).\n"
        'hs.loadSpoon("Penwise")\nspoon.Penwise.bin = "/old/penwise"\nspoon.Penwise.args = {}\n'
        "spoon.Penwise:bindHotkeys({\n"
        '  fix = { { "ctrl", "alt" }, "p" },\n'
        '  improve = { { "ctrl", "alt", "shift" }, "p" },\n'
        "})\n"
        "-- after\n"
    )
    assert setup_mac.write_snippet(init_file) == "updated"
    text = init_file.read_text()
    assert text.count('hs.loadSpoon("Penwise")') == 1
    assert setup_mac.BEGIN in text and "quick = " in text
    assert text.startswith("-- before\n") and text.endswith("-- after\n")


def test_snippet_falls_back_to_python_module(monkeypatch):
    monkeypatch.setattr(setup_mac.shutil, "which", lambda name: None)
    assert 'spoon.Penwise.args = { "-m", "penwise" }' in setup_mac.snippet()


def test_refresh_only_touches_an_installed_hotkey(tmp_path, monkeypatch):
    restarted = []
    monkeypatch.setattr(setup_mac, "hammerspoon_dir", lambda: tmp_path)
    monkeypatch.setattr(setup_mac, "hammerspoon_installed", lambda: True)
    monkeypatch.setattr(setup_mac, "restart_hammerspoon", lambda: restarted.append(True))
    assert setup_mac.refresh() is False  # nothing installed yet: leave it alone
    setup_mac.install_spoon()
    assert setup_mac.refresh() is True
    assert restarted == [True]
    assert "spoon.Penwise:bindHotkeys" in (tmp_path / "init.lua").read_text()


def test_a_block_from_0_2_gets_the_menu_bar_icon(tmp_path):
    init_file = tmp_path / "init.lua"
    setup_mac.write_snippet(init_file)
    init_file.write_text(init_file.read_text().replace("spoon.Penwise:start() -- the ✎ menu bar icon\n", ""))
    assert setup_mac.write_snippet(init_file) == "updated"
    text = init_file.read_text()
    assert text.count("spoon.Penwise:start()") == 1
    assert text.index("spoon.Penwise:start()") < text.index(setup_mac.END)


def test_the_practice_note_opens_in_textedit(tmp_path, monkeypatch):
    opened = []
    monkeypatch.setattr(setup_mac.subprocess, "run", lambda command, **kwargs: opened.append(command))
    path = setup_mac.open_practice_note(tmp_path)
    assert opened == [["open", "-e", str(path)]]
    note = path.read_text(encoding="utf-8")
    assert "[[?]]" in note and "[3]" in note
    assert len(note) <= 2000  # short enough to be checked whole, without selecting


def test_hotkey_log_shows_the_last_lines(tmp_path, monkeypatch):
    log = tmp_path / "penwise-hotkey.log"
    monkeypatch.setattr(setup_mac, "HOTKEY_LOG", log)
    assert setup_mac.hotkey_log() == []
    log.write_text("".join(f"step {n}\n" for n in range(30)))
    assert setup_mac.hotkey_log(3) == ["step 27", "step 28", "step 29"]


def test_the_installer_sets_up_the_hotkey_without_questions(tmp_path, monkeypatch):
    restarted = []
    monkeypatch.setattr(setup_mac, "hammerspoon_dir", lambda: tmp_path)
    monkeypatch.setattr(setup_mac, "hammerspoon_installed", lambda: True)
    monkeypatch.setattr(setup_mac, "restart_hammerspoon", lambda: restarted.append(True))
    setup_mac.install_quietly()
    init = (tmp_path / "init.lua").read_text()
    assert "spoon.Penwise.background = true" in init and init.index("background") < init.index(":start()")
    assert (tmp_path / "Spoons" / "Penwise.spoon" / "init.lua").exists()
    assert restarted == [True]


def test_the_installer_leaves_your_own_hammerspoon_in_sight(tmp_path, monkeypatch):
    monkeypatch.setattr(setup_mac, "hammerspoon_dir", lambda: tmp_path)
    monkeypatch.setattr(setup_mac, "hammerspoon_installed", lambda: True)
    monkeypatch.setattr(setup_mac, "restart_hammerspoon", lambda: None)
    (tmp_path / "init.lua").write_text("hs.hotkey.bind({'cmd'}, 'h', hs.reload)\n")
    setup_mac.install_quietly()
    text = (tmp_path / "init.lua").read_text()
    assert "spoon.Penwise:start()" in text and "background" not in text


def test_hammerspoon_restarts_from_where_it_is(tmp_path, monkeypatch):
    commands, running = [], [True, True, False]  # quits a moment after it's asked to

    def run(command, **kwargs):
        commands.append(command)
        exited = command[0] == "pgrep" and not running.pop(0)
        return setup_mac.subprocess.CompletedProcess(command, 1 if exited else 0)

    app = tmp_path / "Hammerspoon.app"
    app.mkdir()
    monkeypatch.setattr(setup_mac, "APP_PATHS", (tmp_path / "missing.app", app))
    monkeypatch.setattr(setup_mac.subprocess, "run", run)
    monkeypatch.setattr(setup_mac.time, "sleep", lambda seconds: None)
    setup_mac.restart_hammerspoon()
    assert [c[0] for c in commands] == ["pgrep", "pkill", "pgrep", "pgrep", "open"]
    assert commands[-1] == ["open", str(app)]  # just downloaded: macOS may not know it by name yet


FEED = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle"><channel>
  <item><title>Version 1.1.1</title>
    <enclosure url="https://github.com/Hammerspoon/hammerspoon/releases/download/1.1.1/Hammerspoon-1.1.1.zip"/>
    <sparkle:minimumSystemVersion>13.0</sparkle:minimumSystemVersion></item>
  <item><title>Version 1.0.0</title>
    <enclosure url="https://github.com/Hammerspoon/hammerspoon/releases/download/1.0.0/Hammerspoon-1.0.0.zip"/>
    <sparkle:minimumSystemVersion>11.0</sparkle:minimumSystemVersion></item>
</channel></rss>"""


def test_the_newest_hammerspoon_that_runs_on_this_mac():
    assert setup_mac.hammerspoon_download(FEED, "15.3.1").endswith("/1.1.1/Hammerspoon-1.1.1.zip")
    assert setup_mac.hammerspoon_download(FEED, "12.7").endswith("/1.0.0/Hammerspoon-1.0.0.zip")
    assert setup_mac.hammerspoon_download(FEED, "10.15") is None


def fake_mac(tmp_path, monkeypatch, *, signed=True):
    """An /Applications you can't install to; downloads and unpacking that only pretend."""
    commands = []
    system, home = tmp_path / "Applications", tmp_path / "home"  # no /Applications at all here
    monkeypatch.setattr(setup_mac, "APP_PATHS", (system / "Hammerspoon.app", home / "Hammerspoon.app"))
    feeds = {setup_mac.HAMMERSPOON_FEED: FEED.encode()}
    monkeypatch.setattr(setup_mac, "_download", lambda url: feeds.get(url, b"zip"))
    monkeypatch.setattr(setup_mac.platform, "mac_ver", lambda: ("15.3", "", ""))

    def run(command, **kwargs):
        commands.append(command)
        if command[0] == "ditto":
            (Path(command[-1]) / "Hammerspoon.app" / "Contents").mkdir(parents=True)
        return subprocess.CompletedProcess(command, 0 if signed or command[0] != "codesign" else 1)

    monkeypatch.setattr(setup_mac.subprocess, "run", run)
    return commands


def test_hammerspoon_is_downloaded_where_you_can_install_apps(tmp_path, monkeypatch):
    commands = fake_mac(tmp_path, monkeypatch)
    app = setup_mac.install_hammerspoon()
    assert app == tmp_path / "home" / "Hammerspoon.app" and app.exists()
    assert [c[0] for c in commands] == ["ditto", "codesign"]


def test_a_damaged_hammerspoon_download_is_removed(tmp_path, monkeypatch):
    fake_mac(tmp_path, monkeypatch, signed=False)
    with pytest.raises(setup_mac.SetupError, match="damaged"):
        setup_mac.install_hammerspoon()
    assert not (tmp_path / "home" / "Hammerspoon.app").exists()


def test_a_page_that_isnt_the_feed_means_no_connection(tmp_path, monkeypatch):
    fake_mac(tmp_path, monkeypatch)
    monkeypatch.setattr(setup_mac, "_download", lambda url: b"<html>Log in to the Wi-Fi")
    with pytest.raises(setup_mac.SetupError, match="internet connection"):
        setup_mac.install_hammerspoon()


def test_the_installer_gets_hammerspoon_when_it_is_missing(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(setup_mac, "hammerspoon_dir", lambda: tmp_path / ".hammerspoon")
    monkeypatch.setattr(setup_mac, "restart_hammerspoon", lambda: None)

    def offline(url):
        raise setup_mac.SetupError("Couldn't download Hammerspoon.")

    monkeypatch.setattr(setup_mac, "_download", offline)
    monkeypatch.setattr(setup_mac, "hammerspoon_installed", lambda: False)
    monkeypatch.setattr(cli.platform, "system", lambda: "Darwin")
    assert cli.main(["setup-mac", "--background"]) == 1
    assert capsys.readouterr().err.strip() == "Couldn't download Hammerspoon."
