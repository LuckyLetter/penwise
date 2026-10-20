"""Keep the API key in the macOS Keychain instead of a file."""

from __future__ import annotations

import contextlib
import getpass
import platform
import shutil
import subprocess

from penwise.config import ConfigError

SERVICE = "penwise"
READ_COMMAND = f"security find-generic-password -s {SERVICE} -w"
_QUIET = {"capture_output": True, "text": True, "timeout": 30}


def available() -> bool:
    return platform.system() == "Darwin" and shutil.which("security") is not None


def save(key: str) -> None:
    """Store (or replace) the key, then read it back to make sure it is there."""
    if not key or any(char in key for char in '"\\\n\r\t '):
        raise ConfigError("That doesn't look like an API key. Copy it again and paste it in one piece.")
    if not (_save_through_stdin(key) or _save_as_argument(key)):
        raise ConfigError("Could not save the key in the Keychain.")


def _save_through_stdin(key: str) -> bool:
    # `security -i` reads the command from stdin, so the key never shows up in the process list.
    command = f'add-generic-password -U -a "{getpass.getuser()}" -s "{SERVICE}" -w "{key}"\n'
    subprocess.run(["security", "-i"], input=command, **_QUIET)
    return read() == key


def _save_as_argument(key: str) -> bool:
    # Fallback: the plain form, where the key is briefly visible to other processes.
    command = ["security", "add-generic-password", "-U", "-a", getpass.getuser(), "-s", SERVICE, "-w", key]
    subprocess.run(command, **_QUIET)
    return read() == key


def read() -> str:
    try:
        out = subprocess.run(["security", "find-generic-password", "-s", SERVICE, "-w"], **_QUIET)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return out.stdout.strip() if out.returncode == 0 else ""


def delete() -> None:
    """Remove the key from the Keychain, if it is there."""
    with contextlib.suppress(OSError, subprocess.TimeoutExpired):
        subprocess.run(["security", "delete-generic-password", "-s", SERVICE], **_QUIET)
