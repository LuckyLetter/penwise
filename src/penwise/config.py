"""Settings, read from a small TOML file.

Every model, local or in the cloud, is reached the same way: an
OpenAI-compatible chat API at `base_url`. Switching models means changing
`base_url`, `model`, and (for cloud services) the API key.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field, fields
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

MODES = ("fix", "improve")

TEMPLATE = """\
# Penwise settings. Docs: https://github.com/LuckyLetter/penwise#configuration
#
# Penwise talks to any OpenAI-compatible chat API, local or in the cloud.
# Pick one block (uncomment it) or keep the default local Ollama setup.

# --- Local: Ollama (default). Install from ollama.com, then: ollama pull gemma3:1b
base_url = "http://localhost:11434/v1"
model = "gemma3:1b"

# --- Local: LM Studio (start its server from the Developer tab)
# base_url = "http://localhost:1234/v1"
# model = "the-model-id-shown-in-lm-studio"

# --- Local: MLX on Apple silicon (pip install mlx-lm; mlx_lm.server --model <repo>)
# base_url = "http://localhost:8080/v1"
# model = "mlx-community/Llama-3.2-1B-Instruct-4bit"

# --- Cloud: OpenRouter, one key for many models (ids at openrouter.ai/models)
# base_url = "https://openrouter.ai/api/v1"
# model = "openai/gpt-6-luna"

# --- Cloud: any other OpenAI-compatible service (OpenAI, Groq, ...)
# base_url = "https://api.openai.com/v1"
# model = "a-model-name-from-your-provider"
#
# API key. Recommended on macOS: keep it in the Keychain, then point Penwise at it:
#   security add-generic-password -a "$USER" -s penwise -w
# api_key_command = "security find-generic-password -s penwise -w"
# Alternatives: api_key_env = "OPENAI_API_KEY"   or   api_key = "sk-..."

# "fix" changes only what is wrong. "improve" also smooths awkward phrasing.
mode = "fix"

# Also ask the model for a one-line reason per change (one extra request).
# Off by default: 1B models often give wrong reasons. Every change still gets a
# fixed note from Penwise. Turn this on when you use a larger or cloud model.
explain = false

# Keep a local log of the changes you accept, to show your recurring patterns
# (`penwise insights`). Stores only the changed words plus a few words around them.
history = true

# Lower is more predictable. Corrections work best between 0 and 0.3.
temperature = 0.2

# How long a cloud model "thinks" before answering (OpenRouter). Lower is faster.
# Leave unset for the model's default; "none" or "low" where the model allows it.
# reasoning_effort = "low"

# Seconds to wait for the model before giving up.
timeout = 60

# Words Penwise should never change, like names and jargon. Add with `penwise keep <word>`.
# keep = ["PyTorch", "ResNet"]
"""


class ConfigError(Exception):
    pass


@dataclass
class Config:
    base_url: str = "http://localhost:11434/v1"
    model: str = "gemma3:1b"
    api_key: str = ""
    api_key_env: str = ""
    api_key_command: str = ""
    mode: str = "fix"
    explain: bool = False
    history: bool = True
    temperature: float = 0.2
    timeout: float = 60
    reasoning_effort: str = ""
    max_chunk_chars: int = 1200
    keep: list[str] = field(default_factory=list)
    path: Path | None = field(default=None, compare=False)

    def resolve_api_key(self) -> str:
        """Find the API key, if any. Local servers usually need none."""
        if self.api_key:
            return self.api_key
        if self.api_key_env:
            value = os.environ.get(self.api_key_env, "")
            if not value:
                raise ConfigError(f"api_key_env is set to {self.api_key_env}, but that environment variable is empty.")
            return value
        if self.api_key_command:
            try:
                out = subprocess.run(self.api_key_command, shell=True, capture_output=True, text=True, timeout=15)
            except subprocess.TimeoutExpired as exc:
                raise ConfigError("api_key_command took too long to answer.") from exc
            if out.returncode != 0 or not out.stdout.strip():
                detail = out.stderr.strip().splitlines()[-1] if out.stderr.strip() else f"exit code {out.returncode}"
                raise ConfigError(f"api_key_command did not print a key ({detail}).")
            return out.stdout.strip()
        return os.environ.get("PENWISE_API_KEY", "")

    def describe_key(self) -> str:
        if self.api_key:
            return "set in the config file"
        if self.api_key_env:
            return f"from ${self.api_key_env}"
        if self.api_key_command:
            return "from api_key_command"
        if os.environ.get("PENWISE_API_KEY"):
            return "from $PENWISE_API_KEY"
        return "none (fine for local models)"


def config_path() -> Path:
    if os.environ.get("PENWISE_CONFIG"):
        return Path(os.environ["PENWISE_CONFIG"]).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(Path.home(), ".config")
    return Path(base) / "penwise" / "config.toml"


SETTINGS = tuple(f.name for f in fields(Config) if f.name != "path")


def load(path: Path | None = None) -> Config:
    path = path or config_path()
    if not path.exists():
        return Config(path=path)
    return _parse(path.read_text(encoding="utf-8"), path)


def _parse(text: str, path: Path) -> Config:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Could not read {path}: {exc}") from exc

    cfg = Config(path=path)
    unknown = sorted(set(data) - set(SETTINGS))
    if unknown:
        raise ConfigError(f"Unknown setting(s) in {path}: {', '.join(unknown)}")
    for name, value in data.items():
        expected = _expected_type(getattr(cfg, name), value)
        if expected:
            raise ConfigError(f"{name} should be {expected} in {path}")
        setattr(cfg, name, value)
    if cfg.mode not in MODES:
        raise ConfigError(f"mode should be one of {', '.join(MODES)} in {path}")
    return cfg


def parse_value(name: str, raw: str) -> bool | float | int | str | list[str]:
    """Turn a value typed on the command line into the setting's type."""
    if name not in SETTINGS:
        raise ConfigError(f"Unknown setting: {name}. Settings: {', '.join(SETTINGS)}")
    default = getattr(Config(), name)
    if isinstance(default, bool):
        words = {
            "true": True,
            "yes": True,
            "on": True,
            "1": True,
            "false": False,
            "no": False,
            "off": False,
            "0": False,
        }
        if raw.lower() not in words:
            raise ConfigError(f"{name} should be true or false")
        return words[raw.lower()]
    if isinstance(default, (int, float)):
        try:
            number = float(raw)
        except ValueError as exc:
            raise ConfigError(f"{name} should be a number") from exc
        return int(number) if number.is_integer() and isinstance(default, int) else number
    if isinstance(default, list):
        return [item.strip() for item in raw.split(",") if item.strip()]
    return raw


def set_values(updates: dict, path: Path | None = None) -> Path:
    """Change settings in the config file, keeping its comments. A value of None removes the setting."""
    path = path or config_path()
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    for name, value in updates.items():
        if name not in SETTINGS:
            raise ConfigError(f"Unknown setting: {name}")
        pattern = re.compile(rf"^\s*{re.escape(name)}\s*=")
        index = next((i for i, line in enumerate(lines) if pattern.match(line)), None)
        if value is None:
            if index is not None:
                del lines[index]
        elif index is None:
            lines.append(f"{name} = {_toml_value(value)}")
        else:
            lines[index] = f"{name} = {_toml_value(value)}"
    text = "\n".join(lines) + "\n"
    _parse(text, path)  # never write a file that would not load
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def write_config(values: dict, path: Path | None = None) -> Path:
    """Write a fresh, short config file with these values (used by `penwise setup`)."""
    path = path or config_path()
    header = (
        "# Penwise settings, written by `penwise setup`.\n"
        "# Change them with `penwise model` and `penwise config set`, or edit this file.\n"
        "# All settings: https://github.com/LuckyLetter/penwise#configuration\n\n"
    )
    body = "".join(f"{name} = {_toml_value(value)}\n" for name, value in values.items() if value is not None)
    _parse(body, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(header + body, encoding="utf-8")
    if "api_key" in values:
        path.chmod(0o600)  # the key is in the file: keep it private
    return path


def _toml_value(value: object) -> str:
    if isinstance(value, list):
        return "[" + ", ".join(json.dumps(str(item), ensure_ascii=False) for item in value) + "]"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    return json.dumps(str(value), ensure_ascii=False)


def _expected_type(default: object, value: object) -> str | None:
    """Describe the expected type if `value` doesn't match the type of `default`."""
    if isinstance(default, list):
        return None if isinstance(value, list) and all(isinstance(v, str) for v in value) else "a list of words"
    if isinstance(default, bool):
        return None if isinstance(value, bool) else "true or false"
    if isinstance(default, (int, float)):
        return None if isinstance(value, (int, float)) and not isinstance(value, bool) else "a number"
    return None if isinstance(value, type(default)) else "a string"


def write_template(path: Path | None = None, force: bool = False) -> Path:
    path = path or config_path()
    if path.exists() and not force:
        raise ConfigError(f"{path} already exists (use --force to overwrite).")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(TEMPLATE, encoding="utf-8")
    return path
