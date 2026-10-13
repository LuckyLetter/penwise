from penwise import setup_mac


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
