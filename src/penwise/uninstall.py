"""Remove Penwise from this Mac: the hotkey, the settings and history, and Penwise itself.

Only what Penwise put there goes, and a folder only once it is empty. Hammerspoon goes to the
Trash only when asked to: the installer may have put it there just for Penwise.
"""

from __future__ import annotations

import contextlib
import re
import shutil
import subprocess
import sys
from pathlib import Path

from penwise import config, history, keychain, setup_mac

_BLOCK = re.compile(rf"\n*{re.escape(setup_mac.BEGIN)}.*?{re.escape(setup_mac.END)}\n?", re.DOTALL)


def run(remove_hammerspoon: bool = False) -> list[str]:
    """Uninstall Penwise; returns what was removed, in plain words."""
    removed = []
    if _remove_hotkey():
        removed.append("the hotkey")
    if _remove_files(_own_files()):
        removed.append("your settings and history")
    if keychain.available() and keychain.read():
        keychain.delete()
        removed.append("the API key in your Keychain")
    if remove_hammerspoon and _trash_hammerspoon():
        removed.append("Hammerspoon (in the Trash)")
    if _uninstall_penwise():
        removed.append("Penwise")
    return removed


def _remove_hotkey() -> bool:
    init_file = setup_mac.hammerspoon_dir() / "init.lua"
    spoon = setup_mac.hammerspoon_dir() / "Spoons" / setup_mac.SPOON_NAME
    found = spoon.exists()
    shutil.rmtree(spoon, ignore_errors=True)
    if init_file.exists():
        text = init_file.read_text(encoding="utf-8")
        rest = _BLOCK.sub("\n", text).strip()
        if rest != text.strip():
            init_file.write_text(rest + "\n" if rest else "", encoding="utf-8")
            found = True
    return found


def _own_files() -> list[Path]:
    settings = config.config_path()
    logs = Path.home() / "Library" / "Logs"
    return [
        settings,
        settings.with_name(settings.name + ".bak"),
        settings.parent / "Try Penwise.txt",  # the practice note
        history.history_path(),
        setup_mac.HOTKEY_LOG,
        logs / "penwise-install.log",
    ]


def _remove_files(paths: list[Path]) -> bool:
    found = False
    for path in paths:
        if path.is_file():
            path.unlink()
            found = True
            with contextlib.suppress(OSError):  # the penwise folder, once nothing else is in it
                path.parent.rmdir()
    return found


def _trash_hammerspoon() -> bool:
    app = next((path for path in setup_mac.APP_PATHS if path.exists()), None)
    if not app:
        return False
    trash = Path.home() / ".Trash"
    trash.mkdir(exist_ok=True)
    target = trash / app.name
    if target.exists():
        target = trash / f"Hammerspoon {len(list(trash.glob('Hammerspoon*.app')))}.app"
    shutil.move(str(app), str(target))
    # Its settings folder, if Penwise's hotkey was all there was in it: empty files and folders only.
    folder = setup_mac.hammerspoon_dir()
    init_file = folder / "init.lua"
    if init_file.exists() and not init_file.read_text(encoding="utf-8").strip():
        init_file.unlink()
    for empty in (folder / "Spoons", folder):
        with contextlib.suppress(OSError):
            empty.rmdir()
    return True


def _uninstall_penwise() -> bool:
    """Remove the penwise command, when uv installed it (the installer does)."""
    if "tools" not in Path(sys.prefix).parts:
        return False
    uv = shutil.which("uv") or str(Path.home() / ".local" / "bin" / "uv")
    if not Path(uv).exists():
        return False
    return subprocess.run([uv, "tool", "uninstall", "penwise"], capture_output=True).returncode == 0


def quit_hammerspoon() -> None:
    subprocess.run(["pkill", "-x", "Hammerspoon"], capture_output=True)
