"""`penwise update`: get the latest version and refresh the hotkey, in one command."""

from __future__ import annotations

import importlib.metadata
import json
import platform
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from penwise import setup_mac


def install_source() -> tuple[str, str]:
    """Where Penwise was installed from: ("directory", path), ("git", url) or ("other", "")."""
    try:
        text = importlib.metadata.distribution("penwise").read_text("direct_url.json")
    except importlib.metadata.PackageNotFoundError:
        text = None
    if not text:
        return "other", ""
    info = json.loads(text)
    url = info.get("url", "")
    if "vcs_info" in info:
        return "git", url
    if url.startswith("file://"):
        return "directory", urllib.request.url2pathname(urllib.parse.urlparse(url).path)
    return "other", url


def installed_with_uv() -> bool:
    return "tools" in Path(sys.prefix).parts and shutil.which("uv") is not None


def run() -> int:
    kind, where = install_source()
    if not installed_with_uv():
        print("Penwise wasn't installed with uv, so update it the way you installed it, for example:")
        print(f"  pip install --upgrade {where or 'penwise'}")
        return 1

    if kind == "directory":
        if (Path(where) / ".git").exists() and not _run(["git", "-C", where, "pull", "--ff-only"]):
            print(f"Could not update the download in {where}. Check it with `git -C {where} status`.")
            return 1
        ok = _run(["uv", "tool", "install", "--reinstall", where])
    else:
        ok = _run(["uv", "tool", "upgrade", "penwise"])
    if not ok:
        return 1

    # The new version may come with a new Spoon; let the newly installed penwise set it up.
    bin_path, args = setup_mac.penwise_command()
    if platform.system() == "Darwin":
        subprocess.run([bin_path, *args, "setup-mac", "--refresh"])
    version = subprocess.run([bin_path, *args, "--version"], capture_output=True, text=True).stdout.strip()
    print(f"✓ Updated: {version}")
    return 0


def _run(command: list[str]) -> bool:
    print(f"$ {' '.join(command)}")
    return subprocess.run(command).returncode == 0
