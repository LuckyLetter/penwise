"""The Mac installer: the app it builds, and its script run with stand-ins for macOS and uv."""

import os
import plistlib
import shutil
import stat
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

import penwise

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "installer"))
import build  # noqa: E402

SCRIPT = ROOT / "installer" / "install.sh"
pytestmark = pytest.mark.skipif(not shutil.which("bash"), reason="needs bash")


def test_the_download_is_one_app_with_this_penwise_inside(tmp_path):
    archive = build.build(tmp_path)
    assert archive.name == "Install-Penwise.zip"
    with zipfile.ZipFile(archive) as zipped:
        names = zipped.namelist()
        info = plistlib.loads(zipped.read("Install Penwise.app/Contents/Info.plist"))
        executable = zipped.getinfo(f"Install Penwise.app/Contents/MacOS/{info['CFBundleExecutable']}")
        script = zipped.read(executable).decode()
    assert stat.S_IMODE(executable.external_attr >> 16) == 0o755  # unzipped on a Mac, it still runs
    assert script == SCRIPT.read_text()
    assert info["CFBundleShortVersionString"] == penwise.__version__
    assert f"Install Penwise.app/Contents/Resources/penwise-{penwise.__version__}-py3-none-any.whl" in names


def test_the_script_is_valid_bash():
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)


# Stand-ins: each writes what it was asked to commands.log. `uv` installs a `penwise` that does
# the same; FAKE_ANSWER is the button clicked in the first dialog, FAKE_SETUP_ERROR makes
# `penwise setup-mac` fail with that message, FAKE_CONFIGURED makes Penwise already set up.
FAKES = {
    "uname": "echo Darwin",
    "pgrep": "exit 0",
    "open": 'echo "open $*" >> "$COMMANDS"',
    "osascript": """shift  # "-": the script comes on stdin
line="$(printf 'dialog %s' "$*" | tr '\\n' ' ')"
echo "$line" >> "$COMMANDS"  # in one write: the progress dialog runs alongside the other commands
cat > /dev/null
case "${!#}" in
  Install) printf '%s' "$FAKE_ANSWER" ;;
  OK) echo OK ;;
esac""",
    "curl": """echo "curl $*" >> "$COMMANDS"
echo 'mkdir -p "$HOME/.local/bin" && cp "$FAKES/uv.real" "$HOME/.local/bin/uv"'""",
    "uv.real": """echo "uv $*" >> "$COMMANDS"
case "$*" in
  "tool install --help") echo "      --managed-python  Require use of uv-managed Python versions" ;;
  "tool dir --bin") echo "$HOME/.local/bin" ;;
  "tool install "*) mkdir -p "$HOME/.local/bin" && cp "$FAKES/penwise.real" "$HOME/.local/bin/penwise" ;;
esac""",
    "penwise.real": """echo "penwise $*" >> "$COMMANDS"
case "$1" in
  --version) echo "penwise 9.9.9" ;;
  settings) echo "{\\"configured\\": ${FAKE_CONFIGURED:-false}}" ;;
  setup-mac)
    if [ -n "${FAKE_SETUP_ERROR:-}" ]; then echo "$FAKE_SETUP_ERROR" >&2; exit 1; fi
    echo "✓ Hotkey installed, and Hammerspoon restarted to load it." ;;
esac""",
}


@pytest.fixture
def mac(tmp_path):
    fakes = tmp_path / "fakes"
    fakes.mkdir()
    for name, body in FAKES.items():
        (fakes / name).write_text(f"#!/bin/bash\n{body}\n")
        (fakes / name).chmod(0o755)
    home = tmp_path / "home"
    home.mkdir()
    env = {
        "HOME": str(home),
        "PATH": f"{fakes}:/usr/bin:/bin",
        "FAKES": str(fakes),
        "COMMANDS": str(tmp_path / "commands.log"),
        "FAKE_ANSWER": "Install",
    }
    return tmp_path, env


def run(script, env, *args, **extra):
    return subprocess.run(["bash", str(script), *args], env={**env, **extra}, capture_output=True, text=True)


def commands(tmp_path):
    log = tmp_path / "commands.log"
    return log.read_text().splitlines() if log.exists() else []


def the_app(tmp_path):
    """The app as it is after unzipping: the script, and the wheel next to it."""
    app = tmp_path / "Downloads" / "Install Penwise.app"
    (app / "Contents" / "MacOS").mkdir(parents=True)
    (app / "Contents" / "Resources").mkdir()
    shutil.copy(SCRIPT, app / "Contents" / "MacOS" / "Install Penwise")
    wheel = app / "Contents" / "Resources" / "penwise-9.9.9-py3-none-any.whl"
    wheel.write_bytes(b"wheel")
    return app / "Contents" / "MacOS" / "Install Penwise", wheel


uv_elsewhere = pytest.mark.skipif(
    any(os.path.exists(path) for path in ("/opt/homebrew/bin/uv", "/usr/local/bin/uv")),
    reason="this computer has uv where the installer looks for it",
)


@uv_elsewhere
def test_the_app_installs_uv_then_the_penwise_it_carries(mac):
    tmp_path, env = mac
    script, wheel = the_app(tmp_path)
    result = run(script, env)
    assert result.returncode == 0, result.stdout
    home = Path(env["HOME"])
    done = commands(tmp_path)
    assert done[0].startswith("dialog Install Penwise Penwise checks your English")
    assert "and Hammerspoon, the free app" in done[0] and done[0].endswith("Cancel Install")
    assert "curl -LsSf https://astral.sh/uv/install.sh" in done
    assert f"uv tool install --force --reinstall --managed-python --python 3.13 {wheel}" in done
    assert "penwise setup-mac --background" in done
    # One more dialog while it works. Penwise isn't set up yet, so then its window opens instead.
    dialogs = [line for line in done[1:] if line.startswith("dialog")]
    assert len(dialogs) == 1 and dialogs[0].startswith("dialog Install Penwise Installing Penwise…")
    log = (home / "Library" / "Logs" / "penwise-install.log").read_text()
    assert "✓ Hotkey installed" in log and "✓ Penwise 9.9.9" in log
    assert result.stdout == ""  # all of it went to the log


def test_cancel_installs_nothing(mac):
    tmp_path, env = mac
    script, _ = the_app(tmp_path)
    assert run(script, env, FAKE_ANSWER="").returncode == 0
    assert [line.split()[0] for line in commands(tmp_path)] == ["dialog"]


def test_a_problem_is_shown_with_the_details_a_click_away(mac):
    tmp_path, env = mac
    script, _ = the_app(tmp_path)
    problem = "Couldn't download Hammerspoon. Check your internet connection."
    result = run(script, env, FAKE_SETUP_ERROR=problem)
    assert result.returncode == 1
    last = commands(tmp_path)[-1]
    assert last == f"dialog Install Penwise Penwise couldn't be installed. {problem} Show Details OK"


def test_running_it_again_updates_penwise_and_says_it_is_ready(mac):
    tmp_path, env = mac
    script, _ = the_app(tmp_path)
    (Path(env["HOME"]) / ".local" / "bin").mkdir(parents=True)
    shutil.copy(Path(env["FAKES"]) / "uv.real", Path(env["HOME"]) / ".local" / "bin" / "uv")
    assert run(script, env, FAKE_CONFIGURED="true").returncode == 0
    done = commands(tmp_path)
    assert not any(line.startswith("curl") for line in done)  # uv was there already
    assert done[-1] == (
        "dialog Install Penwise Penwise 9.9.9 is ready. Press ⌃⌥P in any text box to check your English. OK"
    )


@uv_elsewhere
def test_in_the_terminal_it_shows_its_progress_instead_of_dialogs(mac):
    tmp_path, env = mac
    result = run(SCRIPT, env, "penwise-9.9.9-py3-none-any.whl")
    assert result.returncode == 0
    assert not any(line.startswith("dialog") for line in commands(tmp_path))
    assert "==> Penwise" in result.stdout
    assert result.stdout.rstrip().endswith("Choose a model in the Penwise window, then press ⌃⌥P in any text box.")
