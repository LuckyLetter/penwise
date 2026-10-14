"""`penwise update`: get the latest version and refresh the hotkey, in one command."""

from __future__ import annotations

import importlib.metadata
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

from penwise import __version__, setup_mac
from penwise.llm import ssl_context

# Where Install Penwise, the Mac installer, can be downloaded; its releases also carry the wheel
# that updates an installation made with it.
DOWNLOAD_PAGE = "https://github.com/LuckyLetter/penwise/releases/latest"
LATEST_RELEASE = "https://api.github.com/repos/LuckyLetter/penwise/releases/latest"


def latest_release() -> tuple[str, str] | None:
    """(version, wheel URL) of the newest release, or None when there's none to be seen."""
    request = urllib.request.Request(LATEST_RELEASE, headers={"User-Agent": f"penwise/{__version__}"})
    try:
        with urllib.request.urlopen(request, timeout=10, context=ssl_context()) as response:
            info = json.loads(response.read())
    except (OSError, ValueError):
        return None
    version = str(info.get("tag_name", "")).lstrip("v")
    wheels = [a.get("browser_download_url") for a in info.get("assets", []) if str(a.get("name")).endswith(".whl")]
    return (version, wheels[0]) if version and wheels and wheels[0] else None


def _newer(version: str, than: str) -> bool:
    def parts(text: str) -> tuple[int, ...]:
        return tuple(int(n) for n in re.findall(r"\d+", text))

    return parts(version) > parts(than)


def _direct_url() -> dict:
    """The install record pip and uv keep (PEP 610), or {} if there is none."""
    try:
        text = importlib.metadata.distribution("penwise").read_text("direct_url.json")
    except importlib.metadata.PackageNotFoundError:
        text = None
    return json.loads(text) if text else {}


def install_source() -> tuple[str, str]:
    """Where Penwise was installed from: ("directory", path), ("file", path) for a wheel, as
    Install Penwise installs it, ("git", url) or ("other", "")."""
    info = _direct_url()
    if not info:
        return "other", ""
    url = info.get("url", "")
    if "vcs_info" in info:
        return "git", url
    if url.startswith("file://"):
        path = urllib.request.url2pathname(urllib.parse.urlparse(url).path)
        return ("file" if "archive_info" in info else "directory"), path
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
    elif kind == "file":  # installed with Install Penwise: its releases
        release = latest_release()
        if release and _newer(release[0], __version__):
            return f"version {release[0]}"
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
    if kind == "file":
        return _update_from_release()
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

    _refresh_hotkey()
    bin_path, args = setup_mac.penwise_command()
    version = subprocess.run([bin_path, *args, "--version"], capture_output=True, text=True).stdout.strip()
    print(f"✓ Updated: {version}")
    return 0


def _uv() -> str | None:
    found = shutil.which("uv") or str(Path.home() / ".local" / "bin" / "uv")  # where the installer puts it
    return found if Path(found).exists() else None


def _update_from_release() -> int:
    """Update an installation made with Install Penwise from its newest release, like it did."""
    release = latest_release()
    uv = _uv()
    if not release or not uv:
        print(f"Penwise couldn't update itself. Download the newest Install Penwise and open it: {DOWNLOAD_PAGE}")
        return 1
    version, url = release
    if not _newer(version, __version__):
        print(f"Penwise is up to date ({__version__}).")
        return 0
    with tempfile.TemporaryDirectory() as folder:
        wheel = Path(folder) / url.rsplit("/", 1)[-1]
        try:
            with urllib.request.urlopen(url, timeout=120, context=ssl_context()) as response:
                wheel.write_bytes(response.read())
        except OSError:
            print("Couldn't download the new version. Check your internet connection, then try again.")
            return 1
        # A Python of uv's own, as the installer chose: the one macOS comes with may ask for developer tools.
        help_text = subprocess.run([uv, "tool", "install", "--help"], capture_output=True, text=True).stdout
        managed = "--managed-python" if "--managed-python" in help_text else "--python-preference=only-managed"
        if not _run([uv, "tool", "install", "--force", "--reinstall", managed, "--python", "3.13", str(wheel)]):
            return 1
    # Started from the ✎ menu, the PATH is Hammerspoon's, without uv's tools: as the installer
    # does, put them first, so the hotkey keeps calling `penwise` itself.
    tools = subprocess.run([uv, "tool", "dir", "--bin"], capture_output=True, text=True).stdout.strip()
    if tools:
        os.environ["PATH"] = tools + os.pathsep + os.environ.get("PATH", "")
    _refresh_hotkey()
    print(f"✓ Updated: Penwise {version}")
    return 0


def _refresh_hotkey() -> None:
    """The new version may come with a new Spoon; let the newly installed penwise set it up."""
    bin_path, args = setup_mac.penwise_command()
    if platform.system() == "Darwin":
        subprocess.run([bin_path, *args, "setup-mac", "--refresh"])


def _run(command: list[str]) -> bool:
    print(f"$ {' '.join(command)}")
    return subprocess.run(command).returncode == 0
