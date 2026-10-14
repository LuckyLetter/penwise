"""Ollama, which runs models on your Mac: is it there, start it, and download a model."""

from __future__ import annotations

import json
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

API = "http://localhost:11434/api"
DOWNLOAD_PAGE = "https://ollama.com/download"
APP_PATHS = (Path("/Applications/Ollama.app"), Path.home() / "Applications" / "Ollama.app")


class OllamaError(Exception):
    """A model could not be downloaded; the message says why."""


def running() -> bool:
    try:
        with urllib.request.urlopen(f"{API}/version", timeout=2):
            return True
    except OSError:
        return False


def models() -> set[str]:
    """The models already on this computer, e.g. {"gemma3:1b", "llama3.2:latest"}."""
    try:
        with urllib.request.urlopen(f"{API}/tags", timeout=5) as response:
            return {m["name"] for m in json.loads(response.read()).get("models", [])}
    except (OSError, ValueError, KeyError):
        return set()


def has_model(model: str, installed: set[str]) -> bool:
    return model in installed or f"{model}:latest" in installed  # "llama3.2" is "llama3.2:latest"


def app() -> Path | None:
    return next((path for path in APP_PATHS if path.exists()), None)


def start(wait: float = 30) -> bool:
    """Open the Ollama app and wait until it answers."""
    path = app()
    if not path:
        return False
    subprocess.run(["open", str(path)], capture_output=True)
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        if running():
            return True
        time.sleep(0.5)
    return False


def pull(model: str) -> Iterator[tuple[int, int]]:
    """Download `model`, yielding (bytes done, bytes in all) as it goes."""
    request = urllib.request.Request(
        f"{API}/pull",
        data=json.dumps({"model": model, "name": model}).encode(),  # "name" for older versions
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            for line in response:
                event = json.loads(line or b"{}")
                if "error" in event:
                    raise OllamaError(_explain(model, event["error"]))
                if event.get("total"):
                    yield event.get("completed", 0), event["total"]
    except (OSError, ValueError) as exc:
        raise OllamaError(f"Couldn't download {model}. Check your internet connection, then try again.") from exc


def _explain(model: str, error: str) -> str:
    if "does not exist" in error or "not found" in error:
        return f"Ollama has no model called “{model}”. Check its name at ollama.com/library."
    return f"Couldn't download {model}: {error}"
