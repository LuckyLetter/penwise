"""Install the Hammerspoon Spoon that gives Penwise its hotkey and review panel."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

SPOON_NAME = "Penwise.spoon"
LOAD_LINE = 'hs.loadSpoon("Penwise")'

SNIPPET = """
-- Penwise: select text anywhere, then press ⌃⌥P (fix) or ⌃⌥⇧P (improve).
hs.loadSpoon("Penwise")
spoon.Penwise.bin = "{bin}"
spoon.Penwise.args = {args}
spoon.Penwise:bindHotkeys({{
  fix = {{ {{ "ctrl", "alt" }}, "p" }},
  improve = {{ {{ "ctrl", "alt", "shift" }}, "p" }},
}})
"""


def spoon_source() -> Path:
    return Path(__file__).parent / "hammerspoon" / SPOON_NAME


def hammerspoon_dir() -> Path:
    return Path.home() / ".hammerspoon"


def penwise_command() -> tuple[str, list[str]]:
    """How Hammerspoon should start Penwise: (executable, leading arguments)."""
    found = shutil.which("penwise")
    if found:
        return str(Path(found).absolute()), []
    return sys.executable, ["-m", "penwise"]


def snippet() -> str:
    bin_path, args = penwise_command()
    lua_args = "{ " + ", ".join(f'"{a}"' for a in args) + " }" if args else "{}"
    return SNIPPET.format(bin=bin_path, args=lua_args)


def install_spoon(target_dir: Path | None = None) -> Path:
    target = (target_dir or hammerspoon_dir()) / "Spoons" / SPOON_NAME
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(spoon_source(), target)
    return target


def needs_snippet(init_file: Path) -> bool:
    return not (init_file.exists() and LOAD_LINE in init_file.read_text(encoding="utf-8"))


def add_snippet(init_file: Path) -> None:
    init_file.parent.mkdir(parents=True, exist_ok=True)
    with init_file.open("a", encoding="utf-8") as f:
        f.write(snippet())
