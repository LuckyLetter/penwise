"""`penwise update`: get the latest version and refresh the hotkey, in one command."""

from __future__ import annotations

import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from penwise import setup_mac


def _direct_url() -> dict:
    """The install record pip and uv keep (PEP 610), or {} if there is none."""
    try:
        text = importlib.metadata.distribution("penwise").read_text("direct_url.json")
    except importlib.metadata.PackageNotFoundError:
        text = None
    return json.loads(text) if text else {}


def install_source() -> tuple[str, str]:
    """Where Penwise was installed from: ("directory", path), ("git", url) or ("other", "")."""
    info = _direct_url()
    if not info:
        return "other", ""
    url = info.get("url", "")
    if "vcs_info" in info:
        return "git", url
    if url.startswith("file://"):
        return "directory", urllib.request.url2pathname(urllib.parse.urlparse(url).path)
    return "other", url


def check() -> str | None:
    """Look for a newer version without installing it. Returns e.g. "3 new changes", or None."""
    kind, where = install_source()
    if kind == "directory" and (Path(where) / ".git").exists():
        git = ["git", "-C", where]
        if _quiet([*git, "fetch", "--quiet"]) is None:
            return None
        count = _quiet([*git, "rev-list", "--count", "HEAD..@{u}"]) or "0"
        if count.isdigit() and int(count) > 0:
            return f"{count} new change{'s' if int(count) > 1 else ''}"
    elif kind == "git":
        vcs = _direct_url().get("vcs_info", {})
        remote = _quiet(["git", "ls-remote", where, vcs.get("requested_revision") or "HEAD"]) or ""
        latest = remote.split()[0] if remote else ""
        if latest and latest != vcs.get("commit_id"):
            return "a new version"
    return None


def _quiet(command: list[str]) -> str | None:
    """Run a command without asking anything; return its output, or None if it failed."""
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    try:
        out = subprocess.run(command, capture_output=True, text=True, timeout=30, env=env)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


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
