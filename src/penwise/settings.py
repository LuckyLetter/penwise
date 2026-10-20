"""The settings window on the Mac: the settings as JSON, and saving new ones.

`penwise settings` describes the current settings and the services and models to
choose from; `penwise settings --save` saves what the window sends and tries the
model, so the window can say at once whether it works. For a model on this Mac it
first gets Ollama ready: it starts the app and downloads the model if needed.
"""

from __future__ import annotations

import http.client
import json
import os
import re
import time
import urllib.parse
import urllib.request
from collections.abc import Callable

from penwise import config, engine, i18n, keychain, ollama, presets
from penwise.config import Config, ConfigError
from penwise.i18n import tr
from penwise.llm import ChatClient, LLMError, api_base, less_thinking, ssl_context

TEST_SENTENCE = "This sentence have a error."
# A test slower than this says that a model which doesn't think before answering is quicker.
SLOW_SECONDS = 5
# OpenRouter's reasoning levels, least first.
EFFORTS = ("none", "minimal", "low", "medium", "high", "xhigh", "max")
# Models that aren't for chat, kept out of the suggestions.
_NOT_CHAT = re.compile(r"embed|tts|whisper|dall-e|moderation|audio|image|realtime|transcribe|rerank", re.IGNORECASE)


def describe() -> dict:
    """The current settings, and the services and models to choose from."""
    try:
        cfg = config.load()
    except ConfigError:
        cfg = Config()
    provider = presets.provider_for(cfg.base_url) or presets.CUSTOM
    return {
        "configured": config.model_chosen(),
        "provider": provider.key,
        "base_url": cfg.base_url,
        "model": cfg.model,
        "has_key": bool(cfg.api_key or cfg.api_key_env or cfg.api_key_command),
        # Penwise's windows and notes: in this language, and the ones to choose from.
        "language": cfg.language,
        "languages": [{"code": code, "name": name} for code, name in i18n.languages().items()],
        # For the window to fill in: the address that goes with a key.
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
    base_url = api_base(request.get("base_url") or provider.base_url)
    if provider is presets.CUSTOM:  # an API: maybe one Penwise knows, like OpenRouter
        provider = presets.provider_for(base_url) or presets.CUSTOM
    model = (request.get("model") or "").strip()
    key = (request.get("key") or "").strip()
    if not base_url:
        return _not_saved(tr("Enter the API Endpoint."))
    if not model:
        return _not_saved(tr("Paste your model name."))
    if provider is presets.OPENROUTER and key and not key.startswith("sk-or-"):
        return _not_saved(tr("That doesn't look like an OpenRouter key: it starts with sk-or-."))
    if provider.needs_key and not key and not describe()["has_key"]:
        return _not_saved(tr("Paste your API Key."))

    updates: dict = {
        "base_url": base_url,
        "model": model,
        "explain": presets.explains_well(provider, base_url),
        # Tried by the test below, and kept only if the model takes it.
        "less_thinking": less_thinking_setting(base_url, model),
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
            return {"saved": True, "ok": False, "base_url": base_url, **problem}
        progress(tr("Testing the model…"))
    return {"saved": True, "base_url": base_url, **test()}  # as saved: the window shows it


def _get_ollama_ready(model: str, progress: Callable[[str], None]) -> dict | None:
    """Start Ollama and download the model if needed; return what's wrong, or None."""
    if not ollama.running():
        if not ollama.app():
            return {
                "message": tr(
                    "Models on your Mac run in Ollama, a free app. Download it, open it once, then press Save again."
                ),
                "link": {"label": tr("Download Ollama"), "url": ollama.DOWNLOAD_PAGE},
            }
        progress(tr("Starting Ollama…"))
        if not ollama.start():
            return {"message": tr("Ollama didn't start. Open it from your Applications folder, then press Save again.")}
    if ollama.has_model(model, ollama.models()):
        return None
    progress(tr("Downloading {model}…", model=model))
    shown = -1
    try:
        for done, total in ollama.pull(model):
            if total < 1_000_000:  # the model's small parts (its license, ...) take no time
                continue
            percent = done * 100 // total
            if percent != shown:  # a line per percent, not per packet
                shown = percent
                progress(
                    tr("Downloading {model}… {percent}% of {size}", model=model, percent=percent, size=_size(total))
                )
    except ollama.OllamaError as exc:
        return {"message": str(exc)}
    return None


def _size(count: int) -> str:
    return f"{count / 1e9:.1f} GB" if count >= 1e9 else f"{count / 1e6:.0f} MB"


def list_models(request: dict) -> dict:
    """The chat models a service offers to this key (its /models list), for the window to suggest.

    Without a key, the saved one is used when the address is the saved one. Any problem: no list.
    The list comes back with the address as it was asked for, for the window to match it.
    """
    asked = (request.get("base_url") or "").strip().rstrip("/")
    base_url = api_base(asked)
    key = (request.get("key") or "").strip()
    if not base_url.startswith(("http://", "https://")):
        return {"base_url": asked, "models": []}
    if not key:
        try:
            cfg = config.load()
            if api_base(cfg.base_url) == base_url:
                key = cfg.resolve_api_key()
        except ConfigError:
            pass
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    try:
        with urllib.request.urlopen(
            urllib.request.Request(base_url + "/models", headers=headers), timeout=10, context=ssl_context()
        ) as response:
            data = json.loads(response.read())
    except (OSError, ValueError, http.client.HTTPException):  # HTTPException: "api example.com", say
        return {"base_url": asked, "models": []}
    entries = data.get("data", []) if isinstance(data, dict) else []
    ids = {str(m.get("id", "")).removeprefix("models/") for m in entries if isinstance(m, dict)}
    return {"base_url": asked, "models": sorted(i for i in ids if i and not _NOT_CHAT.search(i))[:100]}


def _not_saved(message: str) -> dict:
    return {"ok": False, "saved": False, "message": message}


def test() -> dict:
    """Try the model on a sentence with two mistakes. When it refuses the setting that makes it think
    less, it is tried without, and that is remembered: no check asks it again."""
    try:
        cfg = config.load()
        client = ChatClient.from_config(cfg)
        started = time.monotonic()
        result = engine.check(TEST_SENTENCE, client.chat, mode="fix", model=cfg.model, explain=False)
    except (ConfigError, LLMError) as exc:
        return {"ok": False, "message": str(exc)}
    seconds = round(time.monotonic() - started, 1)
    if client.refused_quicker and cfg.less_thinking.get("send"):
        config.set_values({"less_thinking": {**cfg.less_thinking, "send": {}}})
    answer = {"ok": True, "before": TEST_SENTENCE, "after": result.edited, "seconds": seconds}
    # Slow from a service: most often a model that thinks first. Not on this Mac, where the first
    # answer waits for the model to load.
    slow = seconds >= SLOW_SECONDS and not presets.is_local(cfg.base_url)
    return {**answer, "slow": True} if slow else answer


def less_thinking_setting(base_url: str, model: str) -> dict:
    """The `less_thinking` setting for this model at this endpoint, to try: see quicker_setting."""
    return {"model": model, "endpoint": base_url, "send": quicker_setting(base_url, model)}


def quicker_setting(base_url: str, model: str) -> dict:
    """What to send so the model thinks little before answering: from OpenRouter's own list of its
    models, or as the service documents it (`llm.less_thinking`); {} for nothing."""
    if (urllib.parse.urlparse(base_url).hostname or "").endswith("openrouter.ai"):
        found = _openrouter_reasoning(base_url, model)
        if found is not None:
            return openrouter_setting(found)
    return less_thinking(base_url, model)


def _openrouter_reasoning(base_url: str, model: str) -> dict | None:
    """How the model reasons, as OpenRouter lists it ({} when it doesn't); None when the list can't be had."""
    try:
        with urllib.request.urlopen(api_base(base_url) + "/models", timeout=10, context=ssl_context()) as response:
            entries = json.loads(response.read()).get("data", [])
    except (OSError, ValueError, AttributeError, http.client.HTTPException):
        return None
    reasoning = {entry.get("id"): entry.get("reasoning") for entry in entries if isinstance(entry, dict)}
    found = reasoning.get(model, reasoning.get(model.split(":")[0]))  # "…:free" and the like: the same model
    return found if isinstance(found, dict) else {}


def openrouter_setting(reasoning: dict) -> dict:
    """From how OpenRouter says a model reasons, what makes it think least. A model that thinks only
    when asked is left so: a level would start its thinking."""
    efforts = [effort for effort in EFFORTS if effort in (reasoning.get("supported_efforts") or [])]
    if reasoning.get("mandatory"):  # always thinks: as little as it can
        lowest = next((effort for effort in efforts if effort != "none"), None)
        return {"reasoning": {"effort": lowest}} if lowest else {}
    if reasoning.get("default_enabled") is True and efforts:
        return {"reasoning": {"effort": efforts[0]}}  # "none" when it can stop thinking
    return {}
