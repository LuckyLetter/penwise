import pytest

from penwise import llm
from penwise.llm import ChatClient, LLMError


def test_chat_sends_an_openai_compatible_request(server):
    client = ChatClient(server.url, "gemma3:1b", api_key="secret", temperature=0.1)
    server.reply = lambda body: "Fixed."
    assert client.chat("system prompt", [{"role": "user", "content": "hi"}]) == "Fixed."

    body = server.requests[0]
    assert body["model"] == "gemma3:1b"
    assert body["temperature"] == 0.1
    assert body["messages"][0] == {"role": "system", "content": "system prompt"}
    assert server.headers[0]["Authorization"] == "Bearer secret"


def test_no_key_means_no_authorization_header(server):
    ChatClient(server.url, "m").chat("s", [{"role": "user", "content": "Correct this text:\nhi"}])
    assert "Authorization" not in server.headers[0]


def test_retries_without_temperature_when_the_model_rejects_it(server):
    def reply(body):
        if "temperature" in body:
            raise server.Reject(400, "Unsupported value: 'temperature' does not support 0.2 with this model.")
        return "Fixed."

    server.reply = reply
    assert ChatClient(server.url, "reasoning-model").chat("s", []) == "Fixed."
    assert [("temperature" in body) for body in server.requests] == [True, False]


def test_other_bad_requests_are_not_retried(server):
    server.status = 400
    server.error = {"error": {"message": "context length exceeded"}}
    with pytest.raises(LLMError, match="context length exceeded"):
        ChatClient(server.url, "m").chat("s", [])
    assert len(server.requests) == 1


def test_a_busy_server_is_asked_once_more(server, monkeypatch):
    monkeypatch.setattr(llm, "RETRY_DELAY", 0)

    def reply(body):
        if len(server.requests) == 1:
            raise server.Reject(503, "overloaded")
        return "Fixed."

    server.reply = reply
    assert ChatClient(server.url, "m").chat("s", []) == "Fixed."

    server.status, server.requests = 429, []
    with pytest.raises(LLMError, match="Rate limited"):
        ChatClient(server.url, "m").chat("s", [])
    assert len(server.requests) == 2  # one retry, then the error


def test_missing_model_suggests_a_fix(server):
    server.status = 404
    server.error = {"error": {"message": 'model "x" not found'}}
    with pytest.raises(LLMError, match='model "x" not found'):
        ChatClient(server.url, "x").chat("s", [])


def test_rejected_key_is_explained(server):
    server.status = 401
    with pytest.raises(LLMError, match="refused the API key"):
        ChatClient(server.url, "m").chat("s", [])


def test_unreachable_ollama_says_how_to_start_it():
    with pytest.raises(LLMError, match="Is Ollama running"):
        ChatClient("http://127.0.0.1:11434/v1", "m", timeout=2).chat("s", [])


def test_reasoning_effort_is_sent_and_dropped_if_rejected(server):
    def reply(body):
        if "reasoning" in body:
            raise server.Reject(400, "reasoning is not supported for this model")
        return "Fixed."

    server.reply = reply
    assert ChatClient(server.url, "m", reasoning_effort="none").chat("s", []) == "Fixed."
    assert server.requests[0]["reasoning"] == {"effort": "none"}
    assert "reasoning" not in server.requests[1]


def test_no_reasoning_setting_by_default(server):
    ChatClient(server.url, "m").chat("s", [{"role": "user", "content": "Correct this text:\nhi"}])
    assert "reasoning" not in server.requests[0]


def test_out_of_credits_is_explained(server):
    server.status = 402
    with pytest.raises(LLMError, match="out of credits"):
        ChatClient(server.url, "m").chat("s", [])
