"""The settings window on the Mac: the settings as JSON, and saving new ones.

`penwise settings` describes the current settings and the services and models to
choose from; `penwise settings --save` saves what the window sends and tries the
model, so the window can say at once whether it works. For a model on this Mac it
first gets Ollama ready: it starts the app and downloads the model if needed.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable

from penwise import config, engine, keychain, ollama, presets
from penwise.config import Config, ConfigError
from penwise.llm import ChatClient, LLMError

TEST_SENTENCE = "This sentence have a error."


def describe() -> dict:
    """The current settings, and the services and models to choose from."""
    try:
        cfg = config.load()
    except ConfigError:
        cfg = Config()
    provider = presets.provider_for(cfg.base_url) or presets.CUSTOM
    return {
        "configured": config.config_path().exists(),
        "provider": provider.key,
        "base_url": cfg.base_url,
        "model": cfg.model,
        "has_key": bool(cfg.api_key or cfg.api_key_env or cfg.api_key_command),
        # For the window to fill in: the models already on this Mac, and the address that goes
        # with a key.
        "installed": sorted(name for name in ollama.models() if "embed" not in name),
        "key_prefixes": [{"prefix": prefix, "base_url": url} for prefix, url in presets.KEY_PREFIXES],
        "providers": [
            {
                "key": p.key,
                "name": p.name,
                "blurb": p.blurb,
                "base_url": p.base_url,
                "key_url": p.key_url,
                "models": [{"id": m.id, "blurb": m.blurb} for m in p.models],
            }
            for p in presets.PROVIDERS
        ],
    }


def save(request: dict, progress: Callable[[str], None] = lambda text: None) -> dict:
    """Save the settings from the window, then try the model. Returns what the window shows.

    `progress` hears what takes a while, like "Downloading gemma3:1b… 40% of 815 MB".
    """
    provider = next((p for p in presets.PROVIDERS if p.key == request.get("provider")), presets.CUSTOM)
    base_url = (request.get("base_url") or provider.base_url).strip()
    if provider is presets.CUSTOM:  # an API: maybe one Penwise knows, like OpenRouter
        provider = presets.provider_for(base_url) or presets.CUSTOM
    model = (request.get("model") or "").strip()
    key = (request.get("key") or "").strip()
    if not base_url:
        return _not_saved("Enter the service's address (it usually ends in /v1).")
    if not model:
        return _not_saved("Choose a model.")
    if provider is presets.OPENROUTER and key and not key.startswith("sk-or-"):
        return _not_saved("That doesn't look like an OpenRouter key: it starts with sk-or-.")
    if provider.needs_key and not key and not describe()["has_key"]:
        return _not_saved("Paste your API key.")

    updates: dict = {
        "base_url": base_url,
        "model": model,
        "reasoning_effort": presets.reasoning_effort_for(model) or None,
        "explain": presets.explains_well(provider, base_url),
    }
    if key:
        if keychain.available():
            keychain.save(key)
            updates.update(api_key_command=keychain.READ_COMMAND, api_key=None, api_key_env=None)
        else:
            updates.update(api_key=key, api_key_command=None, api_key_env=None)
    path = config.set_values(updates)
    if updates.get("api_key"):
        os.chmod(path, 0o600)  # the key is in the file: readable only by you
    if provider is presets.OLLAMA and base_url == presets.OLLAMA.base_url:
        problem = _get_ollama_ready(model, progress)
        if problem:
            return {"saved": True, "ok": False, **problem}
        progress("Testing the model…")
    return {"saved": True, **test()}


def _get_ollama_ready(model: str, progress: Callable[[str], None]) -> dict | None:
    """Start Ollama and download the model if needed; return what's wrong, or None."""
    if not ollama.running():
        if not ollama.app():
            return {
                "message": "Models on your Mac run in Ollama, a free app. Download it, open it once, "
                "then press Save again.",
                "link": {"label": "Download Ollama", "url": ollama.DOWNLOAD_PAGE},
            }
        progress("Starting Ollama…")
        if not ollama.start():
            return {"message": "Ollama didn't start. Open it from your Applications folder, then press Save again."}
    if ollama.has_model(model, ollama.models()):
        return None
    progress(f"Downloading {model}…")
    shown = -1
    try:
        for done, total in ollama.pull(model):
            if total < 1_000_000:  # the model's small parts (its license, ...) take no time
                continue
            percent = done * 100 // total
            if percent != shown:  # a line per percent, not per packet
                shown = percent
                progress(f"Downloading {model}… {percent}% of {_size(total)}")
    except ollama.OllamaError as exc:
        return {"message": str(exc)}
    return None


def _size(count: int) -> str:
    return f"{count / 1e9:.1f} GB" if count >= 1e9 else f"{count / 1e6:.0f} MB"


def _not_saved(message: str) -> dict:
    return {"ok": False, "saved": False, "message": message}


def test() -> dict:
    """Try the model on a sentence with two mistakes."""
    try:
        cfg = config.load()
        client = ChatClient.from_config(cfg)
        started = time.monotonic()
        result = engine.check(TEST_SENTENCE, client.chat, mode="fix", model=cfg.model, explain=False)
    except (ConfigError, LLMError) as exc:
        return {"ok": False, "message": str(exc)}
    seconds = round(time.monotonic() - started, 1)
    return {"ok": True, "before": TEST_SENTENCE, "after": result.edited, "seconds": seconds}
