"""Penwise.app: its two scripts, run with stand-ins for macOS, and how it is built and zipped."""

import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

import penwise

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "installer"))
import build_app  # noqa: E402

pytestmark = pytest.mark.skipif(not shutil.which("bash"), reason="needs bash")
BASH = os.environ.get("PENWISE_TEST_BASH", "bash")  # macOS has bash 3.2

# Stand-ins: each writes what it was asked to commands.log. A dialog (osascript -l JavaScript -
# LANGUAGE-FILE TEXT DETAIL BUTTONS…) is written in the language of that file, as macOS shows it,
# or in English from AppleScript (osascript - TEXT DETAIL BUTTONS…); FAKE_ANSWER 1 is its Cancel
# button, FAKE_NO_JAVASCRIPT a Mac where the JavaScript doesn't run.
FAKES = {
    "osascript": r"""cat > /dev/null
if [ "$1" = -l ]; then
  [ -z "${FAKE_NO_JAVASCRIPT:-}" ] || { echo "execution error: SyntaxError (-2700)" >&2; exit 1; }
  file="$4"; shift 4
else
  file=""; shift
fi
text="$(python3 -I -c 'import json, sys
try: print(json.load(open(sys.argv[1]))["strings"].get(sys.argv[2], sys.argv[2]))
except Exception: print(sys.argv[2])' "$file" "$1")"
echo "dialog $text${2:+ $2}" >> "$COMMANDS"
[ "${FAKE_ANSWER:-0}" = 0 ] || { echo "execution error: User canceled. (-128)" >&2; exit 1; }
""",
    "xattr": 'echo "xattr $*" >> "$COMMANDS"',
    # Unzipping Hammerspoon makes it; copying copies.
    "ditto": """echo "ditto $*" >> "$COMMANDS"
if [ "$1" = -x ]; then mkdir -p "$4/Hammerspoon.app"; else mkdir -p "$2" && cp -R "$1/." "$2/"; fi""",
    "pkill": 'echo "pkill $*" >> "$COMMANDS"',
    "pgrep": 'test -n "${FAKE_RUNNING:-}"',
    # Penwise, in Hammerspoon, takes Penwise.app's note as it opens its window. FAKE_SILENT: it
    # doesn't, at the link ("link") or at all ("all").
    "open": """echo "open $*" >> "$COMMANDS"
if [ "$2" = hammerspoon://penwiseSettings ] && [ -z "${FAKE_SILENT:-}" ]; then
  rm -f "$HOME/Library/Application Support/Penwise/opened"
fi""",
    "lsregister": 'echo "lsregister $*" >> "$COMMANDS"',  # macOS's list of apps, and their icons
    "uname": 'if [ "$1" = -m ]; then echo x86_64; else echo Darwin; fi',
    "sleep": "true",  # no waiting in tests
}
# The app's Penwise, as the Spoon runs it: here it records how it was started, and setting up the
# shortcut writes the Penwise block and "starts" Hammerspoon, where Penwise takes the app's note.
PENWISE = """echo "penwise $* PENWISE_APP=$PENWISE_APP" >> "$COMMANDS"
if [ "$1" = setup-mac ]; then
  mkdir -p "$HOME/.hammerspoon" && echo 'spoon.Penwise:start()' > "$HOME/.hammerspoon/init.lua"
  touch "$FAKES/running"
  [ "${FAKE_SILENT:-}" = all ] || rm -f "$HOME/Library/Application Support/Penwise/opened"
fi"""


@pytest.fixture
def mac(tmp_path):
    fakes = tmp_path / "fakes"
    fakes.mkdir()
    for name, body in FAKES.items():
        (fakes / name).write_text(f"#!/bin/bash\n{body}\n")
        (fakes / name).chmod(0o755)
    # pgrep: running once the shortcut is set up
    (fakes / "pgrep").write_text('#!/bin/bash\ntest -e "$FAKES/running"\n')
    app = tmp_path / "Applications" / "Penwise.app"
    resources = app / "Contents" / "Resources"
    (app / "Contents" / "MacOS").mkdir(parents=True)
    (resources / "bin").mkdir(parents=True)
    launcher = (ROOT / "installer" / "app" / "launcher.sh").read_text()
    lsregister = next(line for line in launcher.splitlines() if line.startswith("LSREGISTER="))
    (app / "Contents" / "MacOS" / "Penwise").write_text(launcher.replace(lsregister, "LSREGISTER=lsregister"))
    (resources / "bin" / "penwise").write_text(f"#!/bin/bash\n{PENWISE}\n")
    (resources / "bin" / "penwise").chmod(0o755)
    (resources / "version").write_text("9.9.9\n")
    (resources / "hammerspoon-version").write_text("1.1.1\n")
    (resources / "Hammerspoon.zip").write_text("zip")
    home = tmp_path / "home"
    home.mkdir()
    env = {"HOME": str(home), "PATH": f"{fakes}:/usr/bin:/bin", "FAKES": str(fakes), "COMMANDS": str(tmp_path / "log")}
    return app, env


def open_app(app, env):
    subprocess.run([BASH, str(app / "Contents" / "MacOS" / "Penwise")], env=env, check=True, timeout=60)
    log = Path(env["COMMANDS"])
    commands = log.read_text().splitlines() if log.exists() else []
    log.unlink(missing_ok=True)
    return commands


def test_the_first_time_it_sets_penwise_up_with_nothing_to_download(mac):
    app, env = mac
    commands = open_app(app, env)
    support = Path(env["HOME"]) / "Library" / "Application Support" / "Penwise"
    assert not any(c.startswith("dialog") for c in commands)  # it just opens: its icon bounces in the Dock
    assert f"xattr -dr com.apple.quarantine {app}" in commands
    assert f"lsregister -f {app}" in commands  # its icon, not a blank one kept for an earlier Penwise
    assert f"ditto -x -k {app}/Contents/Resources/Hammerspoon.zip {support}" in commands
    assert "penwise setup-mac --background PENWISE_APP=" in commands
    assert (support / "Hammerspoon.app").is_dir()
    assert (support / "app-version").read_text().strip() == f"9.9.9 {app}"
    assert not (support / "opened").exists()  # Penwise, once Hammerspoon started, took the note: its window opens
    assert not any(c.startswith("open") for c in commands)
    log = Path(env["HOME"]) / "Library" / "Logs" / "penwise-install.log"
    assert "✓ Penwise 9.9.9" in log.read_text()


def test_opened_again_it_opens_the_settings(mac):
    app, env = mac
    open_app(app, env)
    assert open_app(app, env) == ["open -g hammerspoon://penwiseSettings"]


def test_opened_again_when_penwise_doesnt_answer_it_sets_it_up_again(mac):
    app, env = mac
    open_app(app, env)
    commands = open_app(app, {**env, "FAKE_SILENT": "link"})  # say, Hammerspoon runs without Penwise
    assert commands[0] == "open -g hammerspoon://penwiseSettings"
    assert any(c.startswith("penwise setup-mac") for c in commands)


def test_penwise_that_doesnt_start_is_said_in_a_dialog(mac):
    app, env = mac
    with pytest.raises(subprocess.CalledProcessError):
        open_app(app, {**env, "FAKE_SILENT": "all"})  # Hammerspoon runs, without Penwise
    commands = Path(env["COMMANDS"]).read_text().splitlines()
    assert commands[-1] == "dialog Penwise didn't start. Open it again."


def test_a_new_version_sets_up_again_and_its_hammerspoon_is_replaced(mac):
    app, env = mac
    open_app(app, env)
    (app / "Contents" / "Resources" / "version").write_text("9.9.10\n")
    (app / "Contents" / "Resources" / "hammerspoon-version").write_text("1.2.0\n")
    commands = open_app(app, env)
    assert "pkill -x Hammerspoon" in commands and any(c.startswith("ditto") for c in commands)
    assert any(c.startswith("penwise setup-mac") for c in commands)


def test_your_own_hammerspoon_is_used(mac):
    app, env = mac
    (Path(env["HOME"]) / "Applications" / "Hammerspoon.app").mkdir(parents=True)
    commands = open_app(app, env)
    assert not any(c.startswith(("ditto", "pkill")) for c in commands)
    assert any(c.startswith("penwise setup-mac") for c in commands)


def opened_from_the_disk_image(tmp_path, app):
    """A copy of the app as on its disk image (in place of /Volumes/Penwise), moving to the
    Applications folder `app` is in (in place of /Applications)."""
    volume = tmp_path / "Volumes"
    shutil.copytree(app, volume / "Penwise.app")
    launcher = volume / "Penwise.app" / "Contents" / "MacOS" / "Penwise"
    script = launcher.read_text().replace("/Volumes/* |", f"{volume}/* |")
    launcher.write_text(script.replace("PLACE=/Applications", f"PLACE={app.parent}"))
    return volume / "Penwise.app"


def test_opened_from_the_disk_image_it_moves_itself_to_applications(tmp_path, mac):
    app, env = mac
    on_the_disk_image = opened_from_the_disk_image(tmp_path, app)
    (app / "Contents" / "Resources" / "version").write_text("0.0.1\n")  # an older Penwise there
    commands = open_app(on_the_disk_image, env)
    assert commands[0] == "dialog Penwise works from your Applications folder. Move it there and open it?"
    assert commands[-1] == f"open {app}"  # and opens from there
    assert f"xattr -dr com.apple.quarantine {app}" in commands
    assert (app / "Contents" / "Resources" / "version").read_text() == "9.9.9\n"  # in place of the old one


def test_run_from_a_hidden_view_of_itself_it_never_loses_the_app(tmp_path, mac):
    app, env = mac
    hidden = tmp_path / "AppTranslocation" / "1234" / "d" / "Penwise.app"  # macOS's view of that very app
    hidden.parent.mkdir(parents=True)
    hidden.symlink_to(app)
    launcher = app / "Contents" / "MacOS" / "Penwise"
    launcher.write_text(launcher.read_text().replace("PLACE=/Applications", f"PLACE={app.parent}"))
    commands = open_app(hidden, env)
    assert commands[-1] == f"open {app}"
    assert launcher.exists() and not (app.parent / "Penwise.app.new").exists()  # still there, and only once


def test_opened_from_the_disk_image_it_moves_nothing_on_cancel(tmp_path, mac):
    app, env = mac
    commands = open_app(opened_from_the_disk_image(tmp_path, app), {**env, "FAKE_ANSWER": "1"})
    assert commands == ["dialog Penwise works from your Applications folder. Move it there and open it?"]


def test_dialogs_are_in_the_language_of_the_settings(tmp_path, mac):
    app, env = mac
    locales = app / "Contents" / "Resources" / "lib" / "penwise" / "hammerspoon" / "Penwise.spoon" / "locales"
    locales.mkdir(parents=True)
    move = "Penwise works from your Applications folder. Move it there and open it?"
    (locales / "xx.json").write_text(json.dumps({"name": "Xx", "strings": {move: "Xx: move?"}}))
    settings = Path(env["HOME"]) / ".config" / "penwise" / "config.toml"
    settings.parent.mkdir(parents=True)
    settings.write_text('model = "m"\nlanguage = "xx"\n')
    on_the_disk_image = opened_from_the_disk_image(tmp_path, app)
    commands = open_app(on_the_disk_image, {**env, "FAKE_ANSWER": "1"})
    assert commands == ["dialog Xx: move?"]
    # Where its script doesn't run, the dialog is still there, in English.
    commands = open_app(on_the_disk_image, {**env, "FAKE_NO_JAVASCRIPT": "1"})
    assert commands[0] == f"dialog {move}" and commands[-1] == f"open {app}"


def test_a_problem_setting_up_is_said_in_a_dialog(mac):
    app, env = mac
    (app / "Contents" / "Resources" / "bin" / "penwise").write_text(
        "#!/bin/bash\necho 'No room on the disk' >&2\nexit 1\n"
    )
    with pytest.raises(subprocess.CalledProcessError):
        open_app(app, env)
    commands = Path(env["COMMANDS"]).read_text().splitlines()
    assert commands[-1].startswith("dialog Penwise couldn't set up its shortcut. No room on the disk")


# The penwise script: the app's own Python, with the app's Penwise or a newer one from an update.


@pytest.fixture
def app_python(tmp_path):
    resources = tmp_path / "Penwise.app" / "Contents" / "Resources"
    (resources / "bin").mkdir(parents=True)
    shutil.copyfile(ROOT / "installer" / "app" / "penwise.sh", resources / "bin" / "penwise")
    (resources / "bin" / "penwise").chmod(0o755)
    (resources / "python" / "bin").mkdir(parents=True)
    (resources / "python" / "bin" / "python3-x86_64").symlink_to(sys.executable)
    shutil.copytree(ROOT / "src" / "penwise", resources / "lib" / "penwise")
    home = tmp_path / "home"
    fakes = tmp_path / "fakes"
    fakes.mkdir()
    (fakes / "uname").write_text("#!/bin/bash\necho x86_64\n")
    (fakes / "uname").chmod(0o755)
    env = {"HOME": str(home), "PATH": f"{fakes}:/usr/bin:/bin", "PENWISE_CONFIG": str(tmp_path / "c.toml")}
    return resources, env, home / "Library" / "Application Support" / "Penwise" / "site"


def run_penwise(resources, env, *args):
    command = [BASH, str(resources / "bin" / "penwise"), *args]
    return subprocess.run(command, env=env, capture_output=True, text=True, check=True).stdout.strip()


def test_the_app_runs_its_own_penwise(app_python):
    resources, env, _ = app_python
    assert run_penwise(resources, env, "--version") == f"penwise {penwise.__version__}"


def test_an_update_is_used_once_newer_than_the_app(app_python):
    resources, env, site = app_python
    (site / "penwise").mkdir(parents=True)
    (site / "penwise" / "__init__.py").write_text('__version__ = "99.0.0"\n')
    says = "import os; print(*(os.environ[n] for n in ('PENWISE_APP', 'PENWISE_COMMAND', 'PYTHONDONTWRITEBYTECODE')))"
    (site / "penwise" / "__main__.py").write_text(says + "\n")
    app = resources.parent.parent
    assert run_penwise(resources, env) == f"{app} {resources}/bin/penwise 1"  # the update, told where it runs
    (site / "penwise" / "__init__.py").write_text('__version__ = "0.0.1"\n')  # the app is newer now
    assert run_penwise(resources, env, "--version") == f"penwise {penwise.__version__}"


# Building it


def test_the_zip_keeps_links_as_links_and_scripts_runnable(tmp_path):
    app = tmp_path / "Penwise.app"
    (app / "Contents" / "MacOS").mkdir(parents=True)
    script = app / "Contents" / "MacOS" / "Penwise"
    script.write_text("#!/bin/bash\n")
    script.chmod(0o755)
    (app / "Contents" / "python3").symlink_to("python3.13")
    archive = build_app.zip_app(app, tmp_path / "Penwise.zip")
    with zipfile.ZipFile(archive) as zipped:
        link = zipped.getinfo("Penwise.app/Contents/python3")
        assert stat.S_ISLNK(link.external_attr >> 16) and zipped.read(link) == b"python3.13"
        assert stat.S_IMODE(zipped.getinfo("Penwise.app/Contents/MacOS/Penwise").external_attr >> 16) == 0o755


def test_the_app_says_what_it_is():
    info = build_app.info_plist("1.2.3")
    assert info["CFBundleExecutable"] == "Penwise" and info["CFBundleShortVersionString"] == "1.2.3"
    assert info["LSMinimumSystemVersion"] == build_app.MIN_MACOS
    assert "LSUIElement" not in info and info["CFBundleIconFile"] == "Penwise"  # in the Dock while it opens
    assert info["CFBundleInfoDictionaryVersion"] == "6.0" and info["CFBundleSignature"] == "????"  # as Xcode writes
    assert (ROOT / "installer" / "app" / "Penwise.icns").read_bytes()[:4] == b"icns"


def fake_python(path, arch):
    """A python-build-standalone download, in small: its program, links to it, pip, the library form."""
    with tarfile.open(path, "w:gz") as archive:

        def add(name, data=b"", link=""):
            info = tarfile.TarInfo(f"python/{name}")
            if link:
                info.type, info.linkname = tarfile.SYMTYPE, link
            else:
                info.size, info.mode = len(data), 0o755
            archive.addfile(info, io.BytesIO(data))

        add("bin/python3.13", arch.encode())
        add("bin/python3", link="python3.13")
        add("bin/pip3", b"pip")
        add("bin/python3.13-config", b"config")
        add("lib/libpython3.13.dylib", arch.encode())
        add("lib/python3.13/os.py", b"# the library")
        add("lib/python3.13/lib-dynload/_dbm.cpython-313-darwin.so", arch.encode())
        add("lib/python3.13/config-3.13-darwin/Makefile", arch.encode())
    return path


def test_one_python_library_serves_both_kinds_of_mac(tmp_path, monkeypatch):
    def download(url, cache):
        arch = "aarch64" if "aarch64" in url else "x86_64"
        return fake_python(tmp_path / f"{arch}.tar.gz", arch)

    monkeypatch.setattr(build_app, "download", download)
    resources = tmp_path / "Resources"
    resources.mkdir()
    build_app.add_python(resources, ("arm64", "x86_64"), tmp_path)
    python = resources / "python"
    assert sorted(path.name for path in (python / "bin").iterdir()) == ["python3-arm64", "python3-x86_64"]
    assert (python / "bin" / "python3-x86_64").read_text() == "x86_64"  # each its own program
    assert (python / "lib" / "python3.13" / "os.py").exists()  # one library
    assert not (python / "lib" / "libpython3.13.dylib").exists()  # the programs have it in themselves
    assert not (python / "lib" / "python3.13" / "config-3.13-darwin").exists()
    assert list((python / "lib" / "python3.13" / "lib-dynload").iterdir()) == []  # there, as Python needs


def test_hammerspoon_is_stored_for_the_disk_image_to_compress(tmp_path, monkeypatch):
    released = tmp_path / "Hammerspoon.zip"
    with zipfile.ZipFile(released, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("Hammerspoon.app/Contents/Info.plist", "<plist/>" * 100)
        link = zipfile.ZipInfo("Hammerspoon.app/Contents/CodeResources")
        link.create_system, link.external_attr = 3, (stat.S_IFLNK | 0o755) << 16
        archive.writestr(link, "_CodeSignature/CodeResources")
    monkeypatch.setattr(build_app, "download", lambda url, cache: released)
    resources = tmp_path / "Resources"
    resources.mkdir()
    build_app.add_hammerspoon(resources, tmp_path)
    with zipfile.ZipFile(released) as before, zipfile.ZipFile(resources / "Hammerspoon.zip") as after:
        assert [e.filename for e in after.infolist()] == [e.filename for e in before.infolist()]
        for entry in after.infolist():
            assert entry.compress_type == zipfile.ZIP_STORED
            assert entry.external_attr == before.getinfo(entry.filename).external_attr  # links stay links
            assert after.read(entry) == before.read(entry.filename)
    assert (resources / "hammerspoon-version").read_text().strip() == build_app.HAMMERSPOON


def test_without_the_tools_for_a_disk_image_the_app_is_zipped(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PATH", str(tmp_path))  # no hdiutil, mkfs.hfsplus, hfsplus or dmg
    monkeypatch.setattr(build_app, "DMG_TOOLS", ("no-such-tool",))
    app = tmp_path / "Penwise.app"
    (app / "Contents").mkdir(parents=True)
    assert build_app.make_dmg(app, tmp_path / "Penwise.dmg") is None
    assert "No disk image: no-such-tool not found" in capsys.readouterr().out


def test_the_disk_image_window_shows_penwise_beside_applications():
    window = (ROOT / "installer" / "app" / "dmg.DS_Store").read_bytes()
    assert window[4:8] == b"Bud1"  # Finder's own format
    for name in ("Penwise.app", "Applications"):  # placed by name, as the disk image has them
        assert name.encode("utf-16-be") in window
