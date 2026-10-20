"""Remove Penwise from this Mac: the hotkey, the settings and history, and Penwise itself.

Only what Penwise put there goes, and a folder only once it is empty. Hammerspoon goes to the
Trash only when asked to: the installer may have put it there just for Penwise.
"""

from __future__ import annotations

import contextlib
import json
import os
import plistlib
import re
import shlex
import shutil
import subprocess
import sys
import urllib.parse
from pathlib import Path

from penwise import config, history, keychain, setup_mac

_BLOCK = re.compile(rf"\n*{re.escape(setup_mac.BEGIN)}.*?{re.escape(setup_mac.END)}\n?", re.DOTALL)


def run(remove_hammerspoon: bool = False) -> list[str]:
    """Uninstall Penwise; returns what was removed, in plain words (Hammerspoon only if it was)."""
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
    app = setup_mac.app_bundle()
    if app:
        # Penwise.app, and its folder: its copy of Hammerspoon and its updates.
        shutil.rmtree(setup_mac.SUPPORT, ignore_errors=True)
        if trash(app):
            removed.append("Penwise")
        forget_in_dock()
    elif _uninstall_penwise():
        removed.append("Penwise")
    return removed


def runs_own_hammerspoon() -> bool:
    """Whether the Hammerspoon running Penwise is Penwise.app's own copy (no other is installed)."""
    others = [path for path in setup_mac.APP_PATHS if path.parent != setup_mac.SUPPORT]
    return setup_mac.app_bundle() is not None and not any(path.exists() for path in others)


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
        logs / "penwise-update.log",
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


def trash(path: Path) -> bool:
    """Move to the Trash as apps do (NSFileManager): macOS keeps other programs out of ~/.Trash,
    and asking the Finder would need a permission. Through osascript's JavaScript, no Apple Events."""
    url = f"$.NSURL.fileURLWithPath({json.dumps(str(path))})"
    script = (
        'ObjC.import("Foundation"); '
        f"$.NSFileManager.defaultManager.trashItemAtURLResultingItemURLError({url}, null, null)"
    )
    subprocess.run(["osascript", "-l", "JavaScript", "-e", script], capture_output=True)
    return not path.exists()


def _trash_hammerspoon() -> bool:
    app = next((path for path in setup_mac.APP_PATHS if path.exists()), None)
    if not app or not trash(app):
        return False
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
    """Remove the penwise command, when uv installed it (an installation from the Terminal)."""
    if "tools" not in Path(sys.prefix).parts:
        return False
    uv = shutil.which("uv") or str(Path.home() / ".local" / "bin" / "uv")
    if not Path(uv).exists():
        return False
    return subprocess.run([uv, "tool", "uninstall", "penwise"], capture_output=True).returncode == 0


APP_ID = "io.github.luckyletter.penwise"  # Penwise.app's (installer/build_app.py)
DOCK = "com.apple.dock"


def forget_in_dock() -> bool:
    """Penwise's place in the Dock, kept there or among the recent apps: it goes with the app.
    Through the Dock's settings (no Apple Events), which it reads again as it restarts."""
    try:
        exported = subprocess.run(["defaults", "export", DOCK, "-"], capture_output=True, check=True).stdout
        prefs = plistlib.loads(exported)
    except (OSError, subprocess.CalledProcessError, plistlib.InvalidFileException, ValueError):
        return False  # not on a Mac, say
    found = False
    for section in ("persistent-apps", "recent-apps"):
        tiles = prefs.get(section)
        if isinstance(tiles, list):
            kept = [tile for tile in tiles if not _is_penwise(tile)]
            found = found or len(kept) < len(tiles)
            prefs[section] = kept
    if not found:
        return False
    subprocess.run(["defaults", "import", DOCK, "-"], input=plistlib.dumps(prefs), capture_output=True)
    subprocess.run(["killall", "Dock"], capture_output=True)
    return True


def _is_penwise(tile: object) -> bool:
    data = tile.get("tile-data") if isinstance(tile, dict) else None
    if not isinstance(data, dict):
        return False
    url = data.get("file-data", {}).get("_CFURLString", "") if isinstance(data.get("file-data"), dict) else ""
    return data.get("bundle-identifier") == APP_ID or urllib.parse.unquote(url).rstrip("/").endswith("/Penwise.app")


def quit_hammerspoon() -> None:
    """Quit it, and forget how Penwise last started it (launchd's job)."""
    with contextlib.suppress(OSError):  # not on a Mac
        job = f"gui/{os.getuid()}/{setup_mac.LAUNCHD_LABEL}"
        subprocess.run(["launchctl", "bootout", job], capture_output=True)
    subprocess.run(["pkill", "-x", "Hammerspoon"], capture_output=True)


HAMMERSPOON_ID = "org.hammerspoon.Hammerspoon"


def forget_hammerspoon() -> None:
    """Once Hammerspoon has quit (it keeps them open till then): its preferences, caches and web
    data, and its Accessibility permission, when macOS lets it go. Nothing is said: you asked for
    it, and it's done."""
    library = Path.home() / "Library"
    folders = [
        library / "Caches" / HAMMERSPOON_ID,
        library / "HTTPStorages" / HAMMERSPOON_ID,
        library / "WebKit" / HAMMERSPOON_ID,
        library / "Saved Application State" / f"{HAMMERSPOON_ID}.savedState",
    ]
    steps = [
        "sleep 2",  # Hammerspoon quits
        f"defaults delete {HAMMERSPOON_ID}",
        *(f"rm -rf {shlex.quote(str(folder))}" for folder in folders),
        f"tccutil reset Accessibility {HAMMERSPOON_ID}",
    ]
    _run_later("; ".join(steps))


def forget_penwise_in_hammerspoon() -> None:
    """Your own Hammerspoon stays: only what Penwise kept in its settings goes."""
    for key in ("penwise.version", "penwise.hotkeyLetter"):
        with contextlib.suppress(OSError):  # not on a Mac
            subprocess.run(["defaults", "delete", HAMMERSPOON_ID, key], capture_output=True)


def _run_later(script: str) -> None:
    """Run a shell script on its own: it outlives Hammerspoon, which started this command."""
    subprocess.Popen(
        ["/bin/sh", "-c", script], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
