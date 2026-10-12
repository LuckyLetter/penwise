"""Keep the API key in the macOS Keychain instead of a file."""

from __future__ import annotations

import getpass
import platform
import shutil
import subprocess

from penwise.config import ConfigError

SERVICE = "penwise"
READ_COMMAND = f"security find-generic-password -s {SERVICE} -w"


def available() -> bool:
    return platform.system() == "Darwin" and shutil.which("security") is not None


def save(key: str) -> None:
    """Store (or replace) the key, then read it back to make sure it is there."""
    if not key or any(char in key for char in '"\\\n\r\t '):
        raise ConfigError("That doesn't look like an API key. Copy it again and paste it in one piece.")
    user = getpass.getuser()
    # `security -i` reads the command from stdin, so the key never shows up in the process list.
    command = f'add-generic-password -U -a "{user}" -s "{SERVICE}" -w "{key}"\n'
    subprocess.run(["security", "-i"], input=command, capture_output=True, text=True, timeout=30)
    if read() == key:
        return
    # Fallback: the plain form, where the key is briefly visible to other processes as an argument.
    add = ["security", "add-generic-password", "-U", "-a", user, "-s", SERVICE, "-w", key]
    subprocess.run(add, capture_output=True, text=True, timeout=30)
    if read() != key:
        raise ConfigError("Could not save the key in the Keychain.")


def read() -> str:
    try:
        out = subprocess.run(READ_COMMAND.split(), capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return out.stdout.strip() if out.returncode == 0 else ""
