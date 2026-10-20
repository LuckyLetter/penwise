import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

FIXES = {
    "have a error": "has an error",
    "untill": "until",
    "informations": "information",
    " [3]": "",  # drops a citation, which Penwise must not apply on its own
}


def fake_edit(text: str) -> str:
    for wrong, right in FIXES.items():
        text = text.replace(wrong, right)
    return text


class Reject(Exception):
    """Raised by a test's `reply` function to answer with an API error."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


class FakeServer:
    """A tiny OpenAI-compatible chat server for tests."""

    Reject = Reject

    def __init__(self):
        self.requests: list[dict] = []
        self.paths: list[str] = []  # where each request went
        self.headers: list[dict] = []
        self.status = 200
        self.error: dict | None = None
        self.reply = self.default_reply
        # What GET /models lists: chat models and others.
        self.models = ["gpt-test-mini", "text-embedding-3-small", "gpt-test", "models/gemini-test-flash"]
        self.model_info: dict[str, dict] = {}  # more about a model, as OpenRouter lists it ("reasoning")
        server = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                server.headers.append(dict(self.headers))
                found = self.path.rstrip("/").endswith("/models")
                entries = [{"id": m, "object": "model", **server.model_info.get(m, {})} for m in server.models]
                data = json.dumps({"data": entries}).encode()
                self.send_response(200 if found else 404)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                server.requests.append(body)
                server.paths.append(self.path)
                server.headers.append(dict(self.headers))
                status = server.status
                if status != 200:
                    payload = server.error or {"error": {"message": "nope"}}
                else:
                    try:
                        payload = {"choices": [{"message": {"role": "assistant", "content": server.reply(body)}}]}
                    except Reject as exc:
                        status, payload = exc.status, {"error": {"message": str(exc)}}
                data = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}/v1"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    @staticmethod
    def default_reply(body: dict) -> str:
        last = body["messages"][-1]["content"]
        if last.startswith("Original:"):
            count = last.count("\n") - 2
            return "\n".join(f"{i}. Reason {i}." for i in range(1, count + 1))
        text = last.split("\n", 1)[1]  # drop the "Correct this text:" line
        return fake_edit(text)

    def close(self):
        self.httpd.shutdown()


@pytest.fixture
def server():
    srv = FakeServer()
    yield srv
    srv.close()


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """Point config and history at a temporary directory."""
    monkeypatch.setenv("PENWISE_CONFIG", str(tmp_path / "config.toml"))
    monkeypatch.setenv("PENWISE_HISTORY", str(tmp_path / "history.jsonl"))
    monkeypatch.delenv("PENWISE_API_KEY", raising=False)
    return tmp_path
