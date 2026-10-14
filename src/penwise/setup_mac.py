"""Install the Hammerspoon Spoon that gives Penwise its hotkeys and review panel."""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from xml.etree import ElementTree

from penwise.llm import ssl_context

SPOON_NAME = "Penwise.spoon"
BEGIN = "-- >>> Penwise"
END = "-- <<< Penwise"
APP_PATHS = (Path("/Applications/Hammerspoon.app"), Path.home() / "Applications" / "Hammerspoon.app")
# What the hotkey did, step by step (never your text); written by the Spoon (Penwise.logFile).
HOTKEY_LOG = Path.home() / "Library" / "Logs" / "penwise-hotkey.log"
ACCESSIBILITY_SETTINGS = "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
# Hammerspoon's own update feed: each version, its download and the macOS it needs, newest first.
HAMMERSPOON_FEED = "https://raw.githubusercontent.com/Hammerspoon/hammerspoon/master/appcast.xml"
_SPARKLE = "{http://www.andymatuschak.org/xml-namespaces/sparkle}"


class SetupError(Exception):
    """Something the hotkey needs could not be set up; the message says what."""


SNIPPET = """{begin} (added by `penwise setup`; you can change the hotkeys below)
hs.loadSpoon("Penwise")
spoon.Penwise.bin = "{bin}"
spoon.Penwise.args = {args}
spoon.Penwise:bindHotkeys({{
  fix = {{ {{ "ctrl", "alt" }}, "p" }},              -- review fixes for the selected text
  improve = {{ {{ "ctrl", "alt", "shift" }}, "p" }}, -- also improve clarity and flow
  quick = {{ {{ "ctrl", "alt", "cmd" }}, "p" }},     -- fix and replace right away, no review
}})
{background}spoon.Penwise:start() -- the ✎ menu bar icon
{end}
"""
BACKGROUND = "spoon.Penwise.background = true -- Hammerspoon out of sight: only the ✎ icon\n"

# The block written by Penwise 0.1, before it had markers.
_OLD_SNIPPET = re.compile(r"\n?-- Penwise: select text anywhere.*?\n\}\)\n", re.DOTALL)


def spoon_source() -> Path:
    return Path(__file__).parent / "hammerspoon" / SPOON_NAME


def hammerspoon_dir() -> Path:
    return Path.home() / ".hammerspoon"


def hammerspoon_installed() -> bool:
    return any(path.exists() for path in APP_PATHS)


def spoon_installed() -> bool:
    return (hammerspoon_dir() / "Spoons" / SPOON_NAME).exists()


def penwise_command() -> tuple[str, list[str]]:
    """How Hammerspoon should start Penwise: (executable, leading arguments)."""
    found = shutil.which("penwise")
    if found:
        return str(Path(found).absolute()), []
    return sys.executable, ["-m", "penwise"]


def _lua_args(args: list[str]) -> str:
    return "{ " + ", ".join(f'"{a}"' for a in args) + " }" if args else "{}"


def snippet(background: bool = False) -> str:
    bin_path, args = penwise_command()
    extra = BACKGROUND if background else ""
    return SNIPPET.format(begin=BEGIN, end=END, bin=bin_path, args=_lua_args(args), background=extra)


def install_spoon(target_dir: Path | None = None) -> Path:
    target = (target_dir or hammerspoon_dir()) / "Spoons" / SPOON_NAME
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(spoon_source(), target)
    return target


def write_snippet(init_file: Path, background: bool = False) -> str:
    """Add or refresh the Penwise block in init.lua. Returns "added", "updated" or "unchanged".

    Inside an existing block only the path to `penwise` is refreshed, so hotkeys
    you changed there are kept. `background` keeps Hammerspoon out of sight (new blocks).
    """
    text = init_file.read_text(encoding="utf-8") if init_file.exists() else ""
    if BEGIN in text:
        bin_path, args = penwise_command()
        new = re.sub(r'(?m)^spoon\.Penwise\.bin = ".*"$', f'spoon.Penwise.bin = "{bin_path}"', text)
        new = re.sub(r"(?m)^spoon\.Penwise\.args = .*$", f"spoon.Penwise.args = {_lua_args(args)}", new)
        if "spoon.Penwise:start()" not in new:  # blocks from 0.2 had no menu bar icon
            new = new.replace(END, "spoon.Penwise:start() -- the ✎ menu bar icon\n" + END, 1)
        status = "unchanged" if new == text else "updated"
    elif _OLD_SNIPPET.search(text):
        new = _OLD_SNIPPET.sub(lambda _: "\n" + snippet(), text, count=1)
        status = "updated"
    else:
        new = text + ("\n" if text and not text.endswith("\n") else "") + ("\n" if text else "") + snippet(background)
        status = "added"
    if new != text:
        init_file.parent.mkdir(parents=True, exist_ok=True)
        init_file.write_text(new, encoding="utf-8")
    return status


def _version(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", text))


def hammerspoon_download(feed: str, macos: str) -> str | None:
    """The download of the newest Hammerspoon in its feed that runs on this version of macOS."""
    for item in ElementTree.fromstring(feed).iter("item"):
        enclosure = item.find("enclosure")
        needs = item.findtext(f"{_SPARKLE}minimumSystemVersion") or "0"
        if enclosure is not None and enclosure.get("url") and _version(needs) <= _version(macos):
            return enclosure.get("url")
    return None


def _download(url: str) -> bytes:
    try:
        with urllib.request.urlopen(url, timeout=60, context=ssl_context()) as response:
            return response.read()
    except (urllib.error.URLError, OSError) as exc:
        raise SetupError("Couldn't download Hammerspoon. Check your internet connection.") from exc


def install_hammerspoon() -> Path:
    """Download Hammerspoon from its releases on GitHub into /Applications (or ~/Applications)."""
    try:
        url = hammerspoon_download(_download(HAMMERSPOON_FEED).decode("utf-8"), platform.mac_ver()[0])
    except (ElementTree.ParseError, UnicodeDecodeError) as exc:  # say, a Wi-Fi login page
        raise SetupError("Couldn't download Hammerspoon. Check your internet connection.") from exc
    if not url:
        raise SetupError("Hammerspoon needs a newer version of macOS.")
    folder = APP_PATHS[0].parent if os.access(APP_PATHS[0].parent, os.W_OK) else APP_PATHS[1].parent
    folder.mkdir(parents=True, exist_ok=True)
    app = folder / "Hammerspoon.app"
    with tempfile.TemporaryDirectory() as temp:
        archive = Path(temp) / "Hammerspoon.zip"
        archive.write_bytes(_download(url))
        # ditto, unlike unzip, keeps the app's links and signature intact.
        unpacked = subprocess.run(["ditto", "-x", "-k", str(archive), str(folder)], capture_output=True)
    if unpacked.returncode != 0 or subprocess.run(["codesign", "--verify", str(app)], capture_output=True).returncode:
        shutil.rmtree(app, ignore_errors=True)
        raise SetupError("The Hammerspoon download was damaged. Please try again.")
    return app


def install_quietly() -> None:
    """Install Hammerspoon if needed, and the hotkey, without asking anything (for the installer).

    When Hammerspoon is there only for Penwise (no config of its own yet), it stays out of sight.
    """
    if not hammerspoon_installed():
        install_hammerspoon()
    install_spoon()
    init_file = hammerspoon_dir() / "init.lua"
    only_penwise = not init_file.exists() or not init_file.read_text(encoding="utf-8").strip()
    write_snippet(init_file, background=only_penwise)
    restart_hammerspoon()


def refresh() -> bool:
    """Update an installed hotkey to this version of Penwise, without asking anything."""
    if not (hammerspoon_installed() and spoon_installed()):
        return False
    install_spoon()
    write_snippet(hammerspoon_dir() / "init.lua")
    restart_hammerspoon()
    return True


def _hammerspoon_running() -> bool:
    return subprocess.run(["pgrep", "-x", "Hammerspoon"], capture_output=True).returncode == 0


def restart_hammerspoon() -> None:
    """Quit and reopen Hammerspoon so it loads the new config."""
    if _hammerspoon_running():
        subprocess.run(["osascript", "-e", 'quit app id "org.hammerspoon.Hammerspoon"'], capture_output=True)
        for _ in range(50):  # opening it while it quits would only bring the old one forward
            if not _hammerspoon_running():
                break
            time.sleep(0.1)
    # By its path: macOS may not know yet about a Hammerspoon the installer just downloaded.
    app = next((path for path in APP_PATHS if path.exists()), None)
    subprocess.run(["open", str(app)] if app else ["open", "-a", "Hammerspoon"], capture_output=True)


def open_accessibility_settings() -> None:
    subprocess.run(["open", ACCESSIBILITY_SETTINGS], capture_output=True)


# A note to try the hotkey on, right after setup: a few typical errors, a citation that
# stays as it is, a [[?]] gap, and words in another language.
PRACTICE_NOTE = """\
Try Penwise here. Click anywhere in this note and press Control+Option+P.

Our method have two advantage. First, it need less data then previous work [3]. \
Second, the results are [[?]] with our hypothesis, and we 公开了 the code.

Click a change to undo it, and press Return to put the fixed text here.
"""


def open_practice_note(directory: Path) -> Path:
    """Write the practice note to `directory` and open it in TextEdit."""
    path = directory / "Try Penwise.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(PRACTICE_NOTE, encoding="utf-8")
    subprocess.run(["open", "-e", str(path)], capture_output=True)
    return path


def hotkey_log(lines: int = 15) -> list[str]:
    """The last lines of the hotkey log, or [] when there is none."""
    try:
        return HOTKEY_LOG.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:]
    except OSError:
        return []
