import dataclasses
import http.server
import threading
import urllib.error

import pytest

from penwise import llm, presets
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
    with pytest.raises(LLMError, match=r"has had too many requests \(429\)\. Wait a moment and try again\."):
        ChatClient(server.url, "m").chat("s", [])
    assert len(server.requests) == 2  # one retry, then the error


def test_missing_model_suggests_a_fix(server):
    server.status = 404
    server.error = {"error": {"message": 'model "x" not found'}}
    with pytest.raises(LLMError, match='model "x" not found') as error:
        ChatClient(server.url, "x").chat("s", [])
    assert "Check the model name in the settings." in str(error.value)


def test_rejected_key_is_explained(server):
    server.status = 401
    with pytest.raises(LLMError, match="refused the API Key") as error:
        ChatClient(server.url, "m").chat("s", [])
    assert "Paste a new one in the settings." in str(error.value) and error.value.in_settings


def test_unreachable_ollama_says_how_to_start_it():
    with pytest.raises(LLMError, match=r"Could not reach Ollama on this Mac\. Is it running\? Open the Ollama app\."):
        ChatClient("http://127.0.0.1:11434/v1", "m", timeout=2).chat("s", [])


def test_no_reasoning_setting_by_default(server):
    ChatClient(server.url, "m").chat("s", [{"role": "user", "content": "Correct this text:\nhi"}])
    assert "reasoning" not in server.requests[0]


def test_out_of_credits_is_explained(server):
    server.status = 402
    with pytest.raises(LLMError, match="out of credits"):
        ChatClient(server.url, "m").chat("s", [])


def test_out_of_credits_links_to_the_page_to_add_them(server, monkeypatch):
    service = dataclasses.replace(presets.OPENROUTER, base_url=server.url)
    monkeypatch.setattr(presets, "PROVIDERS", (service,))
    server.status = 402
    with pytest.raises(LLMError, match="out of credits") as error:
        ChatClient(server.url, "m").chat("s", [])
    assert error.value.link == {"label": "Add credits", "url": "https://openrouter.ai/settings/credits"}


def test_a_service_out_of_reach_is_explained_in_plain_words(monkeypatch):
    def offline(*args, **kwargs):
        raise llm.urllib.error.URLError(OSError(8, "nodename nor servname provided, or not known"))

    monkeypatch.setattr(llm.urllib.request, "urlopen", offline)
    with pytest.raises(LLMError) as error:
        ChatClient("https://openrouter.ai/api/v1", "m").chat("s", [])
    assert (
        str(error.value)
        == "Could not reach openrouter.ai. Check your internet connection, and the API Endpoint in the settings."
    )
    with pytest.raises(LLMError, match=r"^Could not reach the model server on this Mac \(localhost:8080\)"):
        ChatClient("http://localhost:8080/v1", "m").chat("s", [])


def test_a_server_problem_and_a_strange_answer_are_explained_in_plain_words(server, monkeypatch):
    server.status = 500
    with pytest.raises(LLMError, match=r"had a problem \(500\)\. Try again in a moment\.") as error:
        ChatClient(server.url, "m", timeout=5).chat("s", [])
    assert "127.0.0.1" in str(error.value) and "server answered" not in str(error.value)

    client = ChatClient(server.url, "m")
    monkeypatch.setattr(client, "_post_without_rejected", lambda body, quicker=None: {"object": "list", "data": []})
    with pytest.raises(LLMError, match="answered, but not as a chat model does") as error:
        client.chat("s", [])
    assert error.value.in_settings and "{" not in str(error.value)  # no JSON dump


def test_a_web_page_instead_of_an_answer_is_explained_in_plain_words(tmp_path):
    class WebPage(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><body>Welcome</body></html>")

        def log_message(self, *args):
            pass

    site = http.server.HTTPServer(("127.0.0.1", 0), WebPage)
    threading.Thread(target=site.serve_forever, daemon=True).start()
    try:
        with pytest.raises(LLMError) as error:
            ChatClient(f"http://127.0.0.1:{site.server_port}", "m").chat("s", [])
    finally:
        site.shutdown()
    message = str(error.value)
    assert message.startswith("127.0.0.1:") and "didn't answer as a chat model does" in message
    assert "JSON" not in message and "/chat/completions" not in message and error.value.in_settings


def test_only_an_unreachable_service_far_away_points_to_the_settings(monkeypatch):
    def unreachable(*args, **kwargs):
        raise urllib.error.URLError(ConnectionRefusedError())

    monkeypatch.setattr(llm.urllib.request, "urlopen", unreachable)
    with pytest.raises(LLMError) as error:
        ChatClient("http://localhost:11434/v1", "m").chat("s", [])
    assert not error.value.in_settings  # on this Mac: the server isn't running
    with pytest.raises(LLMError) as error:
        ChatClient("https://api.example.com/v1", "m").chat("s", [])
    assert error.value.in_settings  # far away: the address may be wrong


def test_an_endpoint_that_cant_be_an_address_says_to_check_it():
    with pytest.raises(LLMError) as error:  # not a connection error from Python, but the same to the user
        ChatClient("api example.com/v1", "m").chat("s", [])
    assert "Check your internet connection, and the API Endpoint in the settings" in str(error.value)
    assert error.value.in_settings


@pytest.mark.parametrize(
    ("pasted", "base"),
    [
        ("https://api.openai.com/v1", "https://api.openai.com/v1"),
        (" https://api.openai.com/v1/ ", "https://api.openai.com/v1"),
        ("https://api.openai.com/v1/chat/completions", "https://api.openai.com/v1"),
        ("api.deepseek.com/chat/completions", "https://api.deepseek.com"),
        ("https://openrouter.ai/api/v1/models", "https://openrouter.ai/api/v1"),
        ("localhost:11434/v1", "http://localhost:11434/v1"),
        ("127.0.0.1:1234/v1/completions", "http://127.0.0.1:1234/v1"),
        ("", ""),
    ],
)
def test_an_endpoint_is_whatever_was_pasted_tidied_to_the_api_base(pasted, base):
    assert llm.api_base(pasted) == base


def test_chat_works_with_a_whole_request_url_as_the_endpoint(server):
    client = ChatClient(server.url + "/chat/completions", "m")  # a config written by hand, say
    client.chat("Fix the text.", [{"role": "user", "content": "Correct this text:\nWe has it."}])
    assert server.paths == ["/v1/chat/completions"]  # not …/chat/completions/chat/completions


@pytest.mark.parametrize(
    ("base_url", "model", "setting"),
    [
        ("https://api.openai.com/v1", "gpt-5-mini", {"reasoning_effort": "low"}),
        ("https://api.openai.com/v1", "o4-mini", {"reasoning_effort": "low"}),
        ("https://api.openai.com/v1", "gpt-4.1-mini", {}),  # doesn't think: nothing to turn down
        ("https://openrouter.ai/api/v1", "openai/gpt-oss-20b", {"reasoning": {"effort": "low"}}),  # always thinks
        ("https://openrouter.ai/api/v1", "openai/gpt-oss-120b:free", {"reasoning": {"effort": "low"}}),
        ("https://openrouter.ai/api/v1", "mistralai/mistral-small-2603", {}),  # thinks only when asked to
        ("https://openrouter.ai/api/v1", "anthropic/claude-haiku-5.5", {}),  # "low" would turn its thinking on
        ("https://api.groq.com/openai/v1", "openai/gpt-oss-20b", {"reasoning_effort": "low"}),
        ("https://generativelanguage.googleapis.com/v1beta/openai", "gemini-2.5-flash", {"reasoning_effort": "low"}),
        ("https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen3-235b-a22b", {"enable_thinking": False}),
        ("https://dashscope-intl.aliyuncs.com/compatible-mode/v1", "qwen-plus", {"enable_thinking": False}),
        ("https://open.bigmodel.cn/api/paas/v4", "glm-4.6", {"thinking": {"type": "disabled"}}),
        ("https://ark.cn-beijing.volces.com/api/v3", "doubao-seed-1-6-250615", {"thinking": {"type": "disabled"}}),
        ("https://api.deepseek.com", "deepseek-chat", {}),  # a service Penwise has no setting for
        ("http://localhost:11434/v1", "qwen3:4b", {}),
        ("http://localhost:1234/v1", "openai/gpt-oss-20b", {"reasoning_effort": "low"}),  # LM Studio
        ("http://localhost:11434/v1", "gpt-oss:20b", {"reasoning_effort": "low"}),  # Ollama
        ("http://127.0.0.1:1234/v1", "gemma-3-4b", {}),  # can't think: Ollama would refuse it
    ],
)
def test_models_that_think_are_asked_to_think_little(base_url, model, setting):
    assert llm.less_thinking(base_url, model) == setting


def test_a_model_asked_to_think_less_answers_quicker(server, monkeypatch):
    monkeypatch.setattr(llm, "_LESS_THINKING", ((r"^127\.0\.0\.1$", r"", {"thinking": {"type": "disabled"}}),))
    ChatClient(server.url, "glm-test").chat("Fix.", [{"role": "user", "content": "Correct this text:\nWe has it."}])
    assert server.requests[-1]["thinking"] == {"type": "disabled"}


def test_a_model_that_cannot_think_less_is_asked_again_as_it_is(server, monkeypatch):
    monkeypatch.setattr(llm, "_LESS_THINKING", ((r"^127\.0\.0\.1$", r"", {"enable_thinking": False}),))

    def reply(body):
        if "enable_thinking" in body:
            raise server.Reject(400, "This model only works with thinking on")  # says not which setting
        return "We have it."

    server.reply = reply
    answer = ChatClient(server.url, "qwq-test").chat("Fix.", [{"role": "user", "content": "x"}])
    assert answer == "We have it."
    assert ["enable_thinking" in body for body in server.requests] == [True, False]
