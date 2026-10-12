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
    assert setup_mac.needs_snippet(init_file)
    setup_mac.add_snippet(init_file)
    assert not setup_mac.needs_snippet(init_file)
    text = init_file.read_text()
    assert 'hs.loadSpoon("Penwise")' in text
    assert "spoon.Penwise:bindHotkeys" in text


def test_snippet_falls_back_to_python_module(monkeypatch):
    monkeypatch.setattr(setup_mac.shutil, "which", lambda name: None)
    assert 'spoon.Penwise.args = { "-m", "penwise" }' in setup_mac.snippet()
