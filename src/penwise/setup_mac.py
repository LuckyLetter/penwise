"""Install the Hammerspoon Spoon that gives Penwise its hotkeys and review panel."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

SPOON_NAME = "Penwise.spoon"
BEGIN = "-- >>> Penwise"
END = "-- <<< Penwise"
APP_PATHS = (Path("/Applications/Hammerspoon.app"), Path.home() / "Applications" / "Hammerspoon.app")
ACCESSIBILITY_SETTINGS = "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"

SNIPPET = """{begin} (added by `penwise setup`; you can change the hotkeys below)
hs.loadSpoon("Penwise")
spoon.Penwise.bin = "{bin}"
spoon.Penwise.args = {args}
spoon.Penwise:bindHotkeys({{
  fix = {{ {{ "ctrl", "alt" }}, "p" }},              -- review fixes for the selected text
  improve = {{ {{ "ctrl", "alt", "shift" }}, "p" }}, -- also improve clarity and flow
  quick = {{ {{ "ctrl", "alt", "cmd" }}, "p" }},     -- fix and replace right away, no review
}})
spoon.Penwise:start() -- the ✎ menu bar icon
{end}
"""

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


def snippet() -> str:
    bin_path, args = penwise_command()
    return SNIPPET.format(begin=BEGIN, end=END, bin=bin_path, args=_lua_args(args))


def install_spoon(target_dir: Path | None = None) -> Path:
    target = (target_dir or hammerspoon_dir()) / "Spoons" / SPOON_NAME
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(spoon_source(), target)
    return target


def write_snippet(init_file: Path) -> str:
    """Add or refresh the Penwise block in init.lua. Returns "added", "updated" or "unchanged".

    Inside an existing block only the path to `penwise` is refreshed, so hotkeys
    you changed there are kept.
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
        new = text + ("\n" if text and not text.endswith("\n") else "") + ("\n" if text else "") + snippet()
        status = "added"
    if new != text:
        init_file.parent.mkdir(parents=True, exist_ok=True)
        init_file.write_text(new, encoding="utf-8")
    return status


def refresh() -> bool:
    """Update an installed hotkey to this version of Penwise, without asking anything."""
    if not (hammerspoon_installed() and spoon_installed()):
        return False
    install_spoon()
    write_snippet(hammerspoon_dir() / "init.lua")
    restart_hammerspoon()
    return True


def restart_hammerspoon() -> None:
    """Quit and reopen Hammerspoon so it loads the new config."""
    subprocess.run(["osascript", "-e", 'quit app "Hammerspoon"'], capture_output=True)
    time.sleep(1)
    subprocess.run(["open", "-a", "Hammerspoon"], capture_output=True)


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
