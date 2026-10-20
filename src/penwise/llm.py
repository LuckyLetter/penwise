"""One client for every model: the OpenAI-compatible chat completions API.

Ollama, LM Studio, llama.cpp, MLX, OpenAI, OpenRouter, Groq and many others
serve this same API, so local and cloud models go through the same code.
"""

from __future__ import annotations

import http.client
import json
import re
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

from penwise import __version__, presets
from penwise.config import Config
from penwise.i18n import tr


class LLMError(Exception):
    """`in_settings`: the fix is in Penwise's settings (the key, the model, the API endpoint).
    `link`: a page where the fix is instead, as {"label": ..., "url": ...}."""

    def __init__(self, message: str, status: int | None = None, in_settings: bool = False, link: dict | None = None):
        super().__init__(message)
        self.status = status
        self.in_settings = in_settings
        self.link = link


# Settings some models refuse (e.g. reasoning models that only take their default
# temperature). When a model rejects one, the request is sent again without it.
OPTIONAL_SETTINGS = ("temperature",)

# A busy or briefly failing server usually answers the second time.
RETRY_STATUSES = (429, 500, 502, 503, 504)
RETRY_DELAY = 1.0

# Models that "think" before answering take tens of seconds over a sentence's grammar. Each service
# that can is asked to keep that short, in its own documented setting, by its address and the
# model's name: OpenAI's thinking models (gpt-oss among them, which can't stop thinking but can think
# little; on OpenAI's servers or on this Mac) and Gemini to reason little, Qwen (DashScope), GLM
# (Zhipu) and Doubao (Volcengine) not to think. A model that refuses the setting is asked again
# without it.
_LESS_THINKING = (
    (r"(^|\.)api\.openai\.com$", r"^(o\d|gpt-[5-9])", {"reasoning_effort": "low"}),
    (r"(^|\.)openrouter\.ai$", r"^openai/(gpt-oss|o\d|gpt-[5-9])", {"reasoning": {"effort": "low"}}),
    (r"(^|\.)api\.groq\.com$", r"gpt-oss", {"reasoning_effort": "low"}),
    (r"(^|\.)generativelanguage\.googleapis\.com$", r"gemini-(2\.5|[3-9])", {"reasoning_effort": "low"}),
    (r"(^|\.)dashscope(-intl)?\.aliyuncs\.com$", r"qwen", {"enable_thinking": False}),
    (r"(^|\.)(open\.bigmodel\.cn|api\.z\.ai)$", r"glm", {"thinking": {"type": "disabled"}}),
    (r"(^|\.)volces\.com$", r"", {"thinking": {"type": "disabled"}}),
    # On this Mac, LM Studio (0.4.8 and later) and Ollama: only to gpt-oss, which always thinks.
    # Ollama refuses it for a model that can't think.
    (r"^(localhost|127\.0\.0\.1|::1)$", r"gpt-oss", {"reasoning_effort": "low"}),
)


def less_thinking(base_url: str, model: str) -> dict:
    """The setting that asks this service's model to think little, or {} when there is none: as the
    service documents it. Save tries it, and keeps what works (`found_less_thinking`)."""
    host = urllib.parse.urlparse(base_url).hostname or ""
    for service, models, setting in _LESS_THINKING:
        if re.search(service, host) and re.search(models, model.lower()):
            return dict(setting)
    return {}


def found_less_thinking(cfg: Config) -> dict | None:
    """What Save found makes this model think less ({} for nothing), or None when Save hasn't tried
    this model at this endpoint (settings from before, or changed elsewhere)."""
    found = cfg.less_thinking
    if (
        isinstance(found.get("send"), dict)
        and found.get("model") == cfg.model
        and api_base(str(found.get("endpoint", ""))) == api_base(cfg.base_url)
    ):
        return found["send"]
    return None


# The paths of requests, as in a service's examples: pasted as the endpoint, they come off.
_REQUEST_PATH = re.compile(r"/(chat/completions|completions|responses|models)/*$")
_ON_THIS_MAC = re.compile(r"(localhost|127\.0\.0\.1|\[::1\])(:|/|$)")


def api_base(url: str) -> str:
    """The address requests go under, from what was pasted as the API endpoint: a request's whole
    URL, maybe without https:// ("api.openai.com/v1/chat/completions" → "https://api.openai.com/v1")."""
    url = url.strip().rstrip("/")
    if url and "://" not in url:
        url = ("http://" if _ON_THIS_MAC.match(url) else "https://") + url
    return _REQUEST_PATH.sub("", url).rstrip("/")


class ChatClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = "",
        temperature: float = 0.2,
        timeout: float = 60,
        quicker: dict | None = None,
    ):
        self.base_url = api_base(base_url)
        self.model = model
        self.api_key = api_key
        self.temperature = temperature
        self.timeout = timeout
        # What to send so the model thinks less, as Save found; None: as the service documents it.
        self.quicker = quicker
        self.refused_quicker = False  # the model refused it: asked again without

    @classmethod
    def from_config(cls, cfg: Config) -> ChatClient:
        return cls(
            cfg.base_url,
            cfg.model,
            cfg.resolve_api_key(),
            cfg.temperature,
            cfg.timeout,
            found_less_thinking(cfg),
        )

    def chat(self, system: str, messages: list[dict]) -> str:
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, *messages],
            "temperature": self.temperature,
            "stream": False,
        }
        quicker = self.quicker if self.quicker is not None else less_thinking(self.base_url, self.model)
        data = self._post_without_rejected({**body, **quicker}, quicker)
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(
                tr(
                    "{host} answered, but not as a chat model does. Check the API Endpoint in the settings: "
                    "it usually ends in /v1.",
                    host=self._host(),
                ),
                in_settings=True,
            ) from exc
        return content or ""

    def _post_without_rejected(self, body: dict, quicker: dict | None = None) -> dict:
        retried = False
        while True:
            try:
                return self._post("/chat/completions", body)
            except LLMError as exc:
                if exc.status in RETRY_STATUSES and not retried:
                    retried = True
                    time.sleep(RETRY_DELAY)
                    continue
                if exc.status == 400 and quicker:  # this model can't think less: as it is, then
                    body = {key: value for key, value in body.items() if key not in quicker}
                    quicker = None
                    self.refused_quicker = True
                    continue
                rejected = [key for key in OPTIONAL_SETTINGS if key in body and key in str(exc)]
                if exc.status != 400 or not rejected:
                    raise
                del body[rejected[0]]

    def _post(self, path: str, body: dict) -> dict:
        url = self.base_url + path
        headers = {"Content-Type": "application/json", "User-Agent": f"penwise/{__version__}"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(url, json.dumps(body).encode("utf-8"), headers, method="POST")
        if re.search(r"[\x00-\x20\x7f]", self._host()):  # "api example.com": no address, so no connection
            raise LLMError(self._connection_message(), in_settings=True)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout, context=ssl_context()) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            service = presets.provider_for(self.base_url)
            credits = service.credits_url if service and exc.code == 402 else ""
            raise LLMError(
                self._http_error_message(exc),
                status=exc.code,
                in_settings=exc.code in (401, 403, 404),
                link={"label": tr("Add credits"), "url": credits} if credits else None,
            ) from exc
        except (TimeoutError, urllib.error.URLError, http.client.HTTPException) as exc:  # HTTPException: cut off
            reason = getattr(exc, "reason", None)
            if isinstance(exc, TimeoutError) or isinstance(reason, (socket.timeout, TimeoutError)):
                raise LLMError(
                    tr(
                        "The model took longer than {seconds}s to answer. "
                        "Try a shorter text, or a faster model in the settings.",
                        seconds=f"{self.timeout:g}",
                    ),
                    in_settings=True,
                ) from exc
            # Far away, the endpoint in the settings may be wrong; on this Mac, the server isn't running.
            raise LLMError(self._connection_message(), in_settings=not presets.is_local(self.base_url)) from exc
        except json.JSONDecodeError as exc:
            raise LLMError(
                tr(
                    "{host} didn't answer as a chat model does. Check the API Endpoint in the settings: "
                    "it usually ends in /v1.",
                    host=self._host(),
                ),
                in_settings=True,
            ) from exc

    def _host(self) -> str:
        """The service's name in messages: openrouter.ai, localhost:8080."""
        return urllib.parse.urlparse(self.base_url).netloc or self.base_url

    def _connection_message(self) -> str:
        """What went wrong, in plain words: where the model is, and what to check."""
        host = self._host()
        if ":11434" in self.base_url:
            return tr("Could not reach Ollama on this Mac. Is it running? Open the Ollama app.")
        if ":1234" in self.base_url:
            return tr("Could not reach LM Studio on this Mac. Is its server started (Developer tab → Start server)?")
        if presets.is_local(self.base_url):
            return tr("Could not reach the model server on this Mac ({host}). Is it running?", host=host)
        return tr(
            "Could not reach {host}. Check your internet connection, and the API Endpoint in the settings.", host=host
        )

    def _http_error_message(self, exc: urllib.error.HTTPError) -> str:
        detail = ""
        try:
            payload = json.loads(exc.read().decode("utf-8", "replace"))
            err = payload.get("error", payload)
            detail = err.get("message", "") if isinstance(err, dict) else str(err)
        except (ValueError, AttributeError):
            pass
        if exc.code in (401, 403):
            message = tr("The service refused the API Key ({code}). Paste a new one in the settings.", code=exc.code)
        elif exc.code == 402:
            message = tr("Your account is out of credits (402). Add credits on your service's website.")
        elif exc.code == 404:
            if ":11434" in self.base_url:
                hint = tr("To download it, choose it in the settings and press Save.")
            else:
                hint = tr("Check the model name in the settings.")
            missing = tr(
                "{host} has no model “{model}”, or the API Endpoint isn't right.", host=self._host(), model=self.model
            )
            message = f"{missing} {hint}"
        elif exc.code == 429:
            message = tr("{host} has had too many requests (429). Wait a moment and try again.", host=self._host())
        else:
            message = tr("{host} had a problem ({code}). Try again in a moment.", host=self._host(), code=exc.code)
        return f"{message} {detail}".strip()


def ssl_context() -> ssl.SSLContext:
    # Python on macOS does not always find the system certificates, so add certifi's bundle too.
    context = ssl.create_default_context()
    try:
        import certifi

        context.load_verify_locations(cafile=certifi.where())
    except ImportError:  # pragma: no cover
        pass
    return context
