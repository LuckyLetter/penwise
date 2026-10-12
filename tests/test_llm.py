import pytest

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
