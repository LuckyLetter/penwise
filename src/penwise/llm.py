"""One client for every model: the OpenAI-compatible chat completions API.

Ollama, LM Studio, llama.cpp, MLX, OpenAI, OpenRouter, Groq and many others
serve this same API, so local and cloud models go through the same code.
"""

from __future__ import annotations

import json
import socket
import ssl
import urllib.error
import urllib.request

from penwise import __version__
from penwise.config import Config


class LLMError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class ChatClient:
    def __init__(self, base_url: str, model: str, api_key: str = "", temperature: float = 0.2, timeout: float = 60):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.temperature = temperature
        self.timeout = timeout

    @classmethod
    def from_config(cls, cfg: Config) -> ChatClient:
        return cls(cfg.base_url, cfg.model, cfg.resolve_api_key(), cfg.temperature, cfg.timeout)

    def chat(self, system: str, messages: list[dict]) -> str:
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, *messages],
            "temperature": self.temperature,
            "stream": False,
        }
        try:
            data = self._post("/chat/completions", body)
        except LLMError as exc:
            # Some models (reasoning models in particular) only accept their default temperature.
            if exc.status != 400 or "temperature" not in str(exc):
                raise
            del body["temperature"]
            data = self._post("/chat/completions", body)
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"Unexpected answer from {self.base_url}: {json.dumps(data)[:300]}") from exc
        return content or ""

    def _post(self, path: str, body: dict) -> dict:
        url = self.base_url + path
        headers = {"Content-Type": "application/json", "User-Agent": f"penwise/{__version__}"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(url, json.dumps(body).encode("utf-8"), headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout, context=_ssl_context()) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise LLMError(self._http_error_message(exc), status=exc.code) from exc
        except TimeoutError as exc:
            raise LLMError(
                f"The model took longer than {self.timeout:g}s to answer. "
                "Try a shorter selection, or raise `timeout` in the config."
            ) from exc
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, (socket.timeout, TimeoutError)):
                raise LLMError(f"The model took longer than {self.timeout:g}s to answer.") from exc
            raise LLMError(self._connection_message(exc)) from exc
        except json.JSONDecodeError as exc:
            raise LLMError(f"{url} did not answer with JSON. Is base_url right? It usually ends in /v1.") from exc

    def _connection_message(self, exc: urllib.error.URLError) -> str:
        msg = f"Could not reach {self.base_url} ({exc.reason})."
        if ":11434" in self.base_url:
            msg += " Is Ollama running? Open the Ollama app or run `ollama serve`."
        elif ":1234" in self.base_url:
            msg += " Is the LM Studio server started (Developer tab → Start server)?"
        elif "localhost" in self.base_url or "127.0.0.1" in self.base_url:
            msg += " Is your local model server running?"
        return msg

    def _http_error_message(self, exc: urllib.error.HTTPError) -> str:
        detail = ""
        try:
            payload = json.loads(exc.read().decode("utf-8", "replace"))
            err = payload.get("error", payload)
            detail = err.get("message", "") if isinstance(err, dict) else str(err)
        except (ValueError, AttributeError):
            pass
        if exc.code in (401, 403):
            hint = "Check api_key / api_key_command in the config."
            return f"The server refused the API key ({exc.code}). {hint} {detail}".strip()
        if exc.code == 404:
            hint = f" For Ollama, run: ollama pull {self.model}" if ":11434" in self.base_url else ""
            return f"Model or endpoint not found ({self.model} at {self.base_url}).{hint} {detail}".strip()
        if exc.code == 429:
            return f"Rate limited by the server (429). Wait a moment and try again. {detail}".strip()
        return f"The server answered with an error ({exc.code}). {detail}".strip()


def _ssl_context() -> ssl.SSLContext:
    # Python on macOS does not always find the system certificates, so add certifi's bundle too.
    context = ssl.create_default_context()
    try:
        import certifi

        context.load_verify_locations(cafile=certifi.where())
    except ImportError:  # pragma: no cover
        pass
    return context
