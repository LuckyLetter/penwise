"""Drive the review panel in a headless browser (skipped when Playwright is not installed)."""

import json

import pytest

from penwise import engine, i18n, setup_mac

sync_api = pytest.importorskip("playwright.sync_api")

PANEL = setup_mac.spoon_source() / "panel.html"

# Stand-in for Hammerspoon's message handler: collect what the panel sends.
CAPTURE = "window.sent = []; window.webkit = {messageHandlers: {penwise: {postMessage: (m) => window.sent.push(m)}}};"


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # no browser downloaded
            pytest.skip(f"Chromium is not available: {exc}")
        yield browser
        browser.close()


@pytest.fixture
def page(browser):
    page = browser.new_page()
    page.add_init_script(CAPTURE)
    page.goto(PANEL.as_uri())
    yield page
    page.close()


def send(page, event):
    page.evaluate(f"penwise.receive({json.dumps(event)})")


def check_result(original, edited):
    result = engine.check(original, lambda system, messages: edited, model="gemma3:1b", explain=False)
    return result.to_dict()


def sent(page):
    return [m for m in page.evaluate("window.sent") if m["action"] != "size"]


def sizes(page):
    return [m["height"] for m in page.evaluate("window.sent") if m["action"] == "size"]


def test_panel_says_ready_on_load(page):
    assert sent(page) == [{"action": "ready"}]


def test_replace_sends_the_accepted_text(page):
    send(page, {"type": "begin", "original": "She have two dataset.", "mode": "fix"})
    send(page, {"type": "start", "model": "gemma3:1b", "explain": False})
    send(page, check_result("She have two dataset.", "She has two datasets."))
    assert page.locator("li").count() == 2

    page.locator("li").first.click()  # undo "have → has"
    page.keyboard.press("Enter")
    message = sent(page)[-1]
    assert message["action"] == "replace"
    assert message["text"] == "She have two datasets."
    assert [c["after"] for c in message["changes"]] == ["datasets"]


def test_number_keys_toggle_changes_and_escape_cancels(page):
    send(page, {"type": "begin", "original": "a eror", "mode": "fix"})
    send(page, check_result("a eror", "an error"))
    page.keyboard.press("2")
    page.keyboard.press("Meta+c")
    assert sent(page)[-1] == {"action": "copy", "text": "an eror"}
    page.keyboard.press("Escape")
    assert sent(page)[-1] == {"action": "cancel"}


def test_tab_switches_mode(page):
    send(page, {"type": "begin", "original": "Hello.", "mode": "fix"})
    page.keyboard.press("Tab")
    assert sent(page)[-1] == {"action": "mode", "mode": "improve"}


def test_explanations_and_errors_are_shown(page):
    send(page, {"type": "begin", "original": "a eror", "mode": "fix"})
    send(page, check_result("a eror", "an error"))
    send(page, {"type": "explanations", "reasons": {"0": "Vowel sound."}})
    assert "Why: Vowel sound." in page.locator("li").first.inner_text()

    send(page, {"type": "error", "message": "Could not reach the model."})
    assert "Could not reach the model." in page.locator("main").inner_text()
    assert page.locator("#primary").inner_text().startswith("Try again")  # the one button: what comes next
    page.keyboard.press("Enter")
    assert sent(page)[-1] == {"action": "retry", "mode": "fix"}
    page.get_by_role("button", name="Open settings").click()
    assert sent(page)[-1] == {"action": "settings"}


def test_text_is_never_interpreted_as_html(page):
    send(page, {"type": "begin", "original": "<b>x</b>", "mode": "fix"})
    send(page, check_result("<img src=x onerror=alert(1)> is here", "<img src=x onerror=alert(1)> is there"))
    assert page.locator("main img").count() == 0
    assert "<img src=x" in page.locator("main").inner_text()


def test_a_timer_runs_while_checking(page):
    send(page, {"type": "begin", "original": "Some text.", "mode": "fix"})
    assert page.locator("#progress").inner_text() == "Checking…"
    page.wait_for_timeout(1300)
    assert page.locator("#progress").inner_text() == "Checking… 1s"


def test_the_panel_shows_how_long_the_check_took(page):
    send(page, {"type": "begin", "original": "a eror", "mode": "fix"})
    send(page, {"type": "start", "model": "mistralai/mistral-small-2603", "explain": False})
    result = check_result("a eror", "an error")
    result["elapsed_ms"] = 1234
    send(page, result)
    assert page.locator("#model").inner_text() == "mistral-small-2603 · 1.2s"


def test_text_that_needs_no_changes_closes_by_itself(page):
    send(page, {"type": "begin", "original": "All good.", "mode": "fix"})
    send(page, check_result("All good.", "All good."))
    assert "Looks good" in page.locator("main").inner_text()
    page.wait_for_timeout(1700)
    assert sent(page)[-1] == {"action": "cancel"}


def test_interacting_keeps_the_panel_open(page):
    send(page, {"type": "begin", "original": "All good.", "mode": "fix"})
    send(page, check_result("All good.", "All good."))
    page.mouse.down()
    page.mouse.up()
    page.wait_for_timeout(1700)
    assert {"action": "cancel"} not in sent(page)


def test_a_note_shows_plain_text(page):
    send(page, {"type": "note", "title": "Your recurring fixes", "text": "3× in → on"})
    assert page.locator("h2").text_content() == "Your recurring fixes"
    assert page.locator("pre").inner_text() == "3× in → on"
    page.keyboard.press("Tab")
    assert sent(page) == [{"action": "ready"}]  # no mode switch
    page.keyboard.press("Enter")
    assert sent(page)[-1] == {"action": "cancel"}  # Done


def test_risky_changes_start_unapplied(page):
    send(page, {"type": "begin", "original": "Shown in [12], it work.", "mode": "fix"})
    send(page, check_result("Shown in [12], it work.", "Shown, it works."))
    first = page.locator("li").first
    assert "Not applied: it would remove a citation" in first.inner_text()
    page.keyboard.press("Enter")
    assert sent(page)[-1]["text"] == "Shown in [12], it works."
    first.click()  # apply it after all
    page.keyboard.press("Enter")
    assert sent(page)[-1]["text"] == "Shown, it works."


def test_the_period_after_a_held_back_change_is_still_put_in(page):
    send(page, {"type": "begin", "original": "we compare with LLMs", "mode": "fix"})
    send(page, check_result("we compare with LLMs", "We compare with large language models."))
    page.keyboard.press("Enter")
    assert sent(page)[-1]["text"] == "We compare with LLMs."  # the acronym kept, the period added


def test_always_keep_a_word(page):
    send(page, {"type": "begin", "original": "We use Pytorch and a eror.", "mode": "fix"})
    send(page, check_result("We use Pytorch and a eror.", "We use PyTorch and an error."))
    first = page.locator("li").first
    first.get_by_role("button", name="Always keep “Pytorch”").click()
    assert sent(page)[-1] == {"action": "keep", "word": "Pytorch"}
    assert "Kept: Penwise won't change “Pytorch” again." in first.inner_text()
    page.keyboard.press("Enter")
    assert sent(page)[-1]["text"] == "We use Pytorch and an error."


def test_grammar_fixes_offer_no_keep_link(page):
    send(page, {"type": "begin", "original": "They achieve it.", "mode": "fix"})
    send(page, check_result("They achieve it.", "They achieved it."))
    assert page.locator("li .keep button").count() == 0  # no "Always keep" for a grammar fix


def test_insights_view(page):
    send(
        page,
        {
            "type": "insights",
            "total": 7,
            "since": "2026-10-12",
            "categories": [
                {"label": "a or an", "count": 5, "note": "Use “an” before a vowel sound.", "example": "is [a] LLM"},
                {"label": "Prepositions", "count": 2, "note": "Learn them in phrases."},
            ],
            "repeated": [{"pair": "in → on", "count": 2, "example": "results [in] the other hand"}],
        },
    )
    text = page.locator("main").inner_text()
    assert "7 changes you accepted since 2026-10-12" in text
    assert "Use “an” before a vowel sound." in text
    assert "e.g. …is [a] LLM…" in text  # from your own writing
    assert "e.g. …results [in] the other hand…" in text
    assert page.locator(".bar").count() == 2
    assert page.locator("#modes").is_hidden()
    assert page.locator("#primary").inner_text().startswith("Done")


def test_insights_without_history(page):
    send(page, {"type": "insights", "total": 0, "since": "", "categories": [], "repeated": []})
    assert "No history yet" in page.locator("main").inner_text()


def test_the_tone_is_shown_for_improve_and_can_be_changed(page):
    send(page, {"type": "begin", "original": "Hi.", "mode": "improve"})
    send(page, {"type": "start", "model": "m", "explain": False, "style": "email"})
    assert page.locator('#tones [aria-pressed="true"]').inner_text() == "Email"
    page.get_by_role("button", name="Chat").click()
    assert sent(page)[-1] == {"action": "style", "style": "chat"}
    send(page, {"type": "begin", "original": "Hi.", "mode": "fix"})
    assert page.locator("#tones").is_hidden()


def test_first_time_tips(page):
    send(page, {"type": "begin", "original": "a eror", "mode": "fix"})
    send(page, {"type": "start", "model": "m", "explain": False, "tips": True})
    send(page, check_result("a eror", "an error"))
    assert "Click a change to undo it" in page.locator(".tips").inner_text()
    send(page, {"type": "begin", "original": "a eror", "mode": "fix"})
    send(page, {"type": "start", "model": "m", "explain": False, "tips": False})
    send(page, check_result("a eror", "an error"))
    assert page.locator(".tips").count() == 0


def test_the_panel_asks_for_a_window_that_fits(page):
    send(page, {"type": "begin", "original": "a eror", "mode": "fix"})
    short = sizes(page)[-1]
    assert 120 < short < 260
    send(page, check_result("a eror", "an error"))
    assert sizes(page)[-1] > short  # the list of changes needs more room


def test_one_button_does_what_comes_next(page):
    send(page, {"type": "begin", "original": "a eror", "mode": "fix"})
    assert page.locator("footer button:visible").count() == 1
    assert page.locator("#primary").is_disabled()  # still checking
    send(page, check_result("a eror", "an error"))
    assert page.locator("#primary").inner_text().startswith("Replace")
    page.locator("#primary").click()
    assert sent(page)[-1]["action"] == "replace"

    send(page, {"type": "begin", "original": "All good.", "mode": "fix"})
    send(page, check_result("All good.", "All good."))
    assert page.locator("#primary").inner_text().startswith("Done")


def test_a_note_is_shown_once_for_changes_of_the_same_kind(page):
    send(page, {"type": "begin", "original": "We use two dataset and three model.", "mode": "fix"})
    send(page, check_result("We use two dataset and three model.", "We use two datasets and three models."))
    assert page.locator("li").count() == 2
    assert page.locator("li .note").count() == 1  # both are plurals, with the same note

    # A grammar point with a note of its own still shows it.
    send(page, {"type": "begin", "original": "She have two dataset.", "mode": "fix"})
    send(page, check_result("She have two dataset.", "She has two datasets."))
    assert page.locator("li .note").count() == 2


def test_text_that_cant_be_edited_there_is_copied(page):
    send(page, {"type": "begin", "original": "a eror", "mode": "fix", "readonly": True})
    send(page, check_result("a eror", "an error"))
    assert page.locator("#primary").inner_text().startswith("Copy")
    page.keyboard.press("Enter")
    assert sent(page)[-1] == {"action": "copy", "text": "an error"}


SETTINGS = {
    "type": "settings",
    "configured": False,
    "provider": "ollama",
    "base_url": "http://localhost:11434/v1",
    "model": "gemma3:1b",
    "has_key": False,
    "providers": [
        {
            "key": "openrouter",
            "name": "OpenRouter",
            "blurb": "cloud models with one API key (easiest to start)",
            "base_url": "https://openrouter.ai/api/v1",
            "key_url": "https://openrouter.ai/settings/keys",
            "models": [
                {"id": "mistralai/mistral-small-2603", "blurb": "fast, low cost"},
                {"id": "openai/gpt-6-luna", "blurb": "stronger"},
            ],
        },
        {
            "key": "ollama",
            "name": "Ollama",
            "blurb": "free and private: the model runs on this computer",
            "base_url": "http://localhost:11434/v1",
            "key_url": "",
            "models": [{"id": "gemma3:1b", "blurb": "small and quick"}],
        },
        {
            "key": "custom",
            "name": "Another service",
            "blurb": "any OpenAI-compatible API",
            "base_url": "",
            "key_url": "",
            "models": [],
        },
    ],
}


LANGUAGES = [{"code": code, "name": name} for code, name in i18n.languages().items()]


def speak(page, code):
    """What Hammerspoon sends when the language is chosen: its words, from the language's file."""
    data = i18n.locale(code)
    send(page, {"type": "language", "language": code, "tag": data["tag"], "strings": data["strings"]})


def test_the_language_is_chosen_at_the_top_of_the_settings(page):
    send(page, {**SETTINGS, "languages": LANGUAGES})
    page.locator("#base_url").fill("api.example.com/v1")
    assert page.locator("#language").input_value() == "en"
    assert [o["code"] for o in LANGUAGES] == page.locator("#language option").evaluate_all(
        "(options) => options.map((o) => o.value)"
    )
    page.locator("#language").select_option("zh")
    assert sent(page)[-1] == {"action": "language", "language": "zh"}
    speak(page, "zh")  # Hammerspoon answers with the words
    assert "欢迎使用 Penwise" in page.locator("main").inner_text()
    assert page.locator("#primary").inner_text().startswith(i18n.strings("zh")["Save"])
    assert page.locator("#cancel").inner_text() == i18n.strings("zh")["Cancel"]
    assert page.locator("#language").input_value() == "zh"
    assert page.locator("#base_url").input_value() == "api.example.com/v1"  # what you typed stays
    assert page.evaluate("document.documentElement.lang") == "zh-Hans"
    page.keyboard.press("Enter")  # Save, whatever it is called
    assert sent(page)[-1]["action"] == "save-settings"


def test_the_review_speaks_the_language(page):
    speak(page, "zh")
    send(page, {"type": "begin", "original": "She have two dataset.", "mode": "fix"})
    assert page.locator("[data-mode=fix]").inner_text() == i18n.strings("zh")["Fix"]
    assert page.locator("#primary").inner_text().startswith(i18n.strings("zh")["Replace"])
    send(page, check_result("She have two dataset.", "She has two datasets."))
    assert i18n.strings("zh")["{count} changes"].replace("{count}", "2") in page.locator("h2").inner_text()


def test_settings_are_one_form_for_every_service(page):
    send(page, SETTINGS)
    assert "Welcome to Penwise" in page.locator("main").inner_text()
    for field in ("#base_url", "#key", "#model-id"):
        assert page.locator(field).input_value() == ""  # nothing chosen for you
    assert page.get_by_role("button", name="On this Mac").count() == 0  # no choice to make first
    assert page.locator("#primary").inner_text().startswith("Save")
    assert page.locator("#access").count() == 0  # no event says it's off: nothing to ask


def test_settings_ask_for_accessibility_until_it_is_on(page):
    send(page, {**SETTINGS, "access": False})
    assert "Allow Penwise to read and replace text" in page.locator("#access").inner_text()
    page.get_by_role("button", name="Open System Settings").click()
    assert sent(page)[-1]["url"].endswith("Privacy_Accessibility")
    send(page, {"type": "access", "allowed": True})
    assert page.locator("#access").inner_text() == "✓ Penwise can read and replace text."


def test_settings_set_up_an_api_and_test_it(page):
    send(page, SETTINGS)
    page.locator("#base_url").fill("https://openrouter.ai/api/v1")  # a service Penwise knows
    page.get_by_role("button", name="Get a key").click()
    assert sent(page)[-1] == {"action": "open-url", "url": "https://openrouter.ai/settings/keys"}
    page.locator("#key").fill("sk-or-v1-abc")
    assert page.locator("#model-id").input_value() == ""  # no model chosen for you
    page.locator("#model-id").fill("openai/gpt-6-luna")
    page.keyboard.press("Enter")  # Return saves
    assert sent(page)[-1] == {
        "action": "save-settings",
        "settings": {
            "provider": "custom",
            "base_url": "https://openrouter.ai/api/v1",
            "model": "openai/gpt-6-luna",
            "key": "sk-or-v1-abc",
        },
    }
    assert "Saving and testing" in page.locator("main").inner_text()

    send(page, {"type": "saved", "saved": True, "ok": True, "before": "a eror", "after": "an error", "seconds": 1.2})
    assert "It works: “a eror” → “an error” (1.2s)" in page.locator("main").inner_text()
    assert page.locator("#key").get_attribute("placeholder") == "Saved in your Keychain"
    page.keyboard.press("Enter")  # Done
    assert sent(page)[-1] == {"action": "cancel"}


def test_settings_show_an_api_already_set_up(page):
    send(
        page,
        {
            **SETTINGS,
            "configured": True,
            "provider": "openrouter",
            "base_url": "https://openrouter.ai/api/v1",
            "model": "mistralai/mistral-small-2603",
            "has_key": True,
        },
    )
    assert page.locator(".title").text_content() == "Settings"
    assert page.locator("#base_url").input_value() == "https://openrouter.ai/api/v1"
    assert page.locator("#key").get_attribute("placeholder") == "Saved in your Keychain"
    assert page.locator("#model-id").input_value() == "mistralai/mistral-small-2603"


def test_settings_say_what_is_wrong(page):
    send(page, {**SETTINGS, "configured": True})
    assert page.locator("#base_url").input_value() == "http://localhost:11434/v1"
    page.locator("#model-id").fill("gemma3:1b")  # typed again: something to save
    page.locator("#primary").click()
    assert sent(page)[-1]["settings"] == {
        "provider": "custom",
        "base_url": "http://localhost:11434/v1",
        "model": "gemma3:1b",
        "key": "",
    }
    send(page, {"type": "saved", "saved": True, "ok": False, "message": "Is Ollama running?"})
    assert "Is Ollama running?" in page.locator(".error").inner_text()
    assert page.locator("#primary").inner_text().startswith("Save")  # fix it and save again


def test_settings_paste_the_key(page):
    send(page, SETTINGS)
    page.locator("#base_url").fill("https://api.example.com/v1")
    assert page.get_by_role("button", name="Paste").count() == 0  # clicking in the box or ⌘V is enough
    send(page, {"type": "pasted", "text": " secret-key\n"})  # ⌘V, pasted by Penwise
    assert page.locator("#key").input_value() == "secret-key"
    page.locator("#model-id").fill("my-model")
    page.keyboard.press("Tab")  # moves to the next field; no mode switch in the settings
    page.locator("#primary").click()
    assert sent(page)[-1]["settings"] == {
        "provider": "custom",
        "base_url": "https://api.example.com/v1",
        "model": "my-model",
        "key": "secret-key",
    }


def test_settings_close_with_cancel_or_done_when_nothing_changed(page):
    send(page, {**SETTINGS, "configured": True})
    assert page.locator("#primary").inner_text().startswith("Done")  # nothing changed: nothing to save
    assert page.locator("#cancel").is_hidden()  # and one button is enough
    page.locator("#primary").click()
    assert sent(page)[-1] == {"action": "cancel"}
    page.locator("#model-id").fill("llama3.2:3b")
    assert page.locator("#primary").inner_text().startswith("Save")
    page.get_by_role("button", name="Cancel").click()  # next to Save, as in a Mac dialog
    assert sent(page)[-1] == {"action": "cancel"}
    assert page.get_by_role("button", name="Close").count() == 0  # no × in a corner

    send(page, SETTINGS)  # the first time there is always something to save, or Cancel
    assert page.locator("#primary").inner_text().startswith("Save") and page.locator("#cancel").is_visible()
    # As in a Mac alert: side by side, the same size, Cancel on the left and Save on the right.
    cancel, save = page.locator("#cancel").bounding_box(), page.locator("#primary").bounding_box()
    assert cancel["x"] < save["x"] and abs(cancel["width"] - save["width"]) < 1 and cancel["y"] == save["y"]
    footer = page.locator("footer").bounding_box()
    left, right = cancel["x"] - footer["x"], footer["x"] + footer["width"] - (save["x"] + save["width"])
    assert abs(left - right) < 1  # symmetric


def test_settings_say_what_to_enter_in_plain_words(page):
    send(page, SETTINGS)
    text = page.locator("main").inner_text()
    assert "Enter the API details from your AI provider." in text
    assert "OpenAI-compatible" not in text
    assert [label.inner_text() for label in page.locator("label").all()] == ["API Endpoint", "API Key", "Model"]
    address = page.locator("#base_url")
    assert address.input_value() == ""  # a tip, not a value
    assert address.get_attribute("placeholder") == "https://api.example.com/v1"
    assert page.locator("#key").get_attribute("placeholder") == "Paste your API key"
    assert page.locator("#model-id").get_attribute("placeholder") == "Paste your model name"
    assert "Ollama on your Mac:" in text


def test_settings_ollama_on_this_mac_is_one_click_away(page):
    send(page, SETTINGS)
    assert "recommended" not in page.locator("main").inner_text()
    page.get_by_role("button", name="http://localhost:11434/v1").click()  # the tip under the address
    assert page.locator("#base_url").input_value() == "http://localhost:11434/v1"
    assert page.locator("#key-hint").inner_text() == "Not needed for a model on your Mac."
    page.wait_for_timeout(800)  # Ollama lists the models on this Mac, with no key
    assert {"action": "list-models", "settings": {"base_url": "http://localhost:11434/v1", "key": ""}} in sent(page)
    send(page, {"type": "models", "base_url": "http://localhost:11434/v1", "models": ["llama3.2:1b", "qwen3:4b"]})
    assert page.locator("#suggested-models option").count() == 2
    page.locator("#model-id").fill("llama3.2:3b")  # or any other
    page.locator("#primary").click()
    assert sent(page)[-1]["settings"] == {
        "provider": "custom",
        "base_url": "http://localhost:11434/v1",
        "model": "llama3.2:3b",
        "key": "",
    }


def test_settings_show_the_model_download_then_link_to_ollama_when_it_is_missing(page):
    send(page, SETTINGS)  # On this Mac
    page.locator("#primary").click()
    assert page.locator("#saving").inner_text() == "Saving and testing…"
    send(page, {"type": "saving", "text": "Downloading gemma3:1b… 40% of 815 MB"})
    assert page.locator("#saving").inner_text() == "Downloading gemma3:1b… 40% of 815 MB"

    send(
        page,
        {
            "type": "saved",
            "saved": True,
            "ok": False,
            "message": "Models on your Mac run in Ollama, a free app. Download it, then press Save again.",
            "link": {"label": "Download Ollama", "url": "https://ollama.com/download"},
        },
    )
    page.get_by_role("button", name="Download Ollama").click()
    assert sent(page)[-1] == {"action": "open-url", "url": "https://ollama.com/download"}
    page.locator("#primary").click()  # Save again, once it's open
    assert page.locator("#saving").inner_text() == "Saving and testing…"


def test_the_first_time_settings_work_they_say_what_to_do_next(page):
    send(page, {**SETTINGS, "hotkey": "⌃⌥E"})  # not set up yet, and a hotkey of your own
    page.locator("#primary").click()
    send(page, {"type": "saved", "saved": True, "ok": True, "before": "a eror", "after": "an error", "seconds": 0.8})
    assert page.locator("#next").inner_text().startswith("You're all set: click in any text box and press ⌃⌥E.")
    page.get_by_role("button", name="Try it on a practice note").click()
    assert sent(page)[-1] == {"action": "try"}

    send(page, {**SETTINGS, "configured": True})  # later: just the result
    page.locator("#primary").click()
    send(page, {"type": "saved", "saved": True, "ok": True, "before": "a eror", "after": "an error", "seconds": 0.8})
    assert page.locator("#next").count() == 0


def test_settings_you_set_up_stay_as_they_are(page):
    send(page, {**SETTINGS, "configured": True})
    assert page.locator("#model-id").input_value() == "gemma3:1b"
    assert page.locator("#base_url").input_value() == "http://localhost:11434/v1"


KEY_PREFIXES = [
    {"prefix": "sk-or-", "base_url": "https://openrouter.ai/api/v1"},
    {"prefix": "gsk_", "base_url": "https://api.groq.com/openai/v1"},
]


def test_settings_fill_in_the_address_that_goes_with_a_key(page):
    send(page, {**SETTINGS, "key_prefixes": KEY_PREFIXES})
    page.locator("#key").fill("sk-or-v1-abc")
    assert page.locator("#base_url").input_value() == "https://openrouter.ai/api/v1"
    assert page.get_by_role("button", name="Get a key").count() == 1  # and it knows the service
    assert page.locator("#model-id").input_value() == ""  # but chooses no model

    page.locator("#base_url").fill("https://example.org/v1")  # an address you typed stays
    page.locator("#key").fill("gsk_abc")
    assert page.locator("#base_url").input_value() == "https://example.org/v1"

    page.locator("#base_url").fill("")
    send(page, {"type": "pasted", "text": "gsk_abc\n"})  # ⌘V
    assert page.locator("#base_url").input_value() == "https://api.groq.com/openai/v1"


COPIED_KEY = "sk-or-v1-0123456789abcdef"


def test_settings_fill_in_a_key_you_copied_when_you_click_in_the_key_box(page):
    send(page, {**SETTINGS, "key_prefixes": KEY_PREFIXES})
    # Only now: macOS may ask whether Hammerspoon can read the clipboard, and you mean to paste.
    assert {"action": "paste-key", "auto": True} not in sent(page)
    page.locator("#key").focus()  # back from the service's website
    assert sent(page)[-1] == {"action": "paste-key", "auto": True}
    send(page, {"type": "pasted", "text": COPIED_KEY + "\n", "auto": True})
    assert page.locator("#key").input_value() == COPIED_KEY
    assert page.evaluate("document.activeElement.id") == "key"  # the box keeps the keyboard
    # The service's address comes with the key; the model is yours to choose.
    assert page.locator("#base_url").input_value() == "https://openrouter.ai/api/v1"
    assert page.locator("#model-id").input_value() == ""
    assert page.locator("#key-hint").inner_text().startswith("Filled in with the key you copied.")
    page.locator("#model-id").fill("my/model")
    page.locator("#primary").click()
    assert sent(page)[-1]["settings"] == {
        "provider": "custom",
        "base_url": "https://openrouter.ai/api/v1",
        "model": "my/model",
        "key": COPIED_KEY,
    }


def test_settings_fill_in_a_key_only_when_it_is_one_and_none_is_there(page):
    send(page, {**SETTINGS, "key_prefixes": KEY_PREFIXES})
    page.locator("#key").focus()
    send(page, {"type": "pasted", "text": "0123456789abcdefghijklmn", "auto": True})  # not a key
    assert page.locator("#key").input_value() == ""
    page.locator("#key").fill("gsk_typed")
    send(page, {"type": "pasted", "text": COPIED_KEY, "auto": True})
    assert page.locator("#key").input_value() == "gsk_typed"  # never over a key you typed


def test_settings_paste_with_command_v_when_the_window_does_not(page):
    send(page, SETTINGS)
    page.locator("#key").focus()
    page.keyboard.press("Meta+v")  # here, as in Hammerspoon without an Edit menu, nothing is pasted
    page.wait_for_timeout(300)
    assert sent(page)[-1] == {"action": "paste-key"}
    send(page, {"type": "pasted", "text": "my-secret-key"})
    assert page.locator("#key").input_value() == "my-secret-key"

    page.locator("#key").fill("")
    page.locator("#key").focus()
    count = len(sent(page))
    page.locator("#key").dispatch_event("keydown", {"key": "v", "metaKey": True})
    page.locator("#key").dispatch_event("paste")  # the window pasted: nothing more to do
    page.wait_for_timeout(300)
    assert {"action": "paste-key"} not in sent(page)[count:]


def test_settings_leave_a_saved_key_alone(page):
    send(
        page,
        {
            **SETTINGS,
            "configured": True,
            "provider": "custom",
            "has_key": True,
            "key_prefixes": KEY_PREFIXES,
            "base_url": "https://api.example.com/v1",
            "model": "my-model",
        },
    )
    page.locator("#key").focus()
    assert {"action": "paste-key", "auto": True} not in sent(page)
    send(page, {"type": "pasted", "text": COPIED_KEY, "auto": True})
    assert page.locator("#key").input_value() == ""


HOTKEYS = {"fix": "⌃⌥P", "improve": "⌃⌥⇧P", "quick": "⌃⌥⌘P"}


def test_settings_change_the_shortcut_letter(page):
    send(page, {**SETTINGS, "configured": True, "hotkeys": HOTKEYS})
    assert page.locator("#hotkey").input_value() == "P"
    page.locator("#hotkey").select_option("E")  # another app uses ⌃⌥P
    assert page.locator("#hotkey-hint").inner_text() == "⌃⌥⇧E also improves the text · ⌃⌥⌘E fixes it right away"
    page.locator("#primary").click()
    assert sent(page)[-1]["hotkey"] == "e"

    send(page, {**SETTINGS, "hotkeys": HOTKEYS})  # the welcome window keeps to the model
    assert page.locator("#hotkey").count() == 0


def test_an_error_with_a_page_for_the_fix_links_to_it(page):
    send(page, {"type": "begin", "original": "a eror", "mode": "fix"})
    link = {"label": "Add credits", "url": "https://openrouter.ai/settings/credits"}
    send(page, {"type": "error", "message": "Your account is out of credits (402).", "link": link})
    page.get_by_role("button", name="Add credits").click()
    assert sent(page)[-1] == {"action": "open-url", "url": "https://openrouter.ai/settings/credits"}
    assert page.get_by_role("button", name="Open settings").count() == 0  # not where the fix is


def test_uninstalling_takes_a_click_not_return(page):
    send(page, {"type": "uninstall", "hammerspoon": True})
    text = page.locator("main").inner_text()
    assert "everything it put on your Mac" in text and "and Hammerspoon, which Penwise set up" in text
    assert page.locator("#primary").inner_text().startswith("Uninstall")
    page.keyboard.press("Enter")  # the usual next step: not for removing things
    assert not any(message.get("action") == "uninstall" for message in sent(page))
    page.locator("#primary").click()
    assert sent(page)[-1] == {"action": "uninstall", "hammerspoon": True}  # all of it: no box to tick

    send(page, {"type": "uninstall", "hammerspoon": False})  # Hammerspoon was there before Penwise: it stays
    assert "Hammerspoon" not in page.locator("main").inner_text()
    page.locator("#primary").click()
    assert sent(page)[-1] == {"action": "uninstall", "hammerspoon": False}

    send(page, {"type": "uninstall", "hammerspoon": False})
    page.get_by_role("button", name="Cancel").click()  # changed your mind
    assert sent(page)[-1] == {"action": "cancel"}


def test_windows_move_by_their_top_as_by_a_title_bar(page):
    send(page, {**SETTINGS, "configured": True})
    box = page.locator("header").bounding_box()
    page.mouse.move(box["x"] + 100, box["y"] + 5)
    page.mouse.down()
    page.mouse.move(box["x"] + 160, box["y"] + 45)
    page.mouse.up()
    moves = [m["action"] for m in sent(page) if m["action"].startswith("drag")]
    assert moves[0] == "drag-start" and "drag" in moves and moves[-1] == "drag-end"  # Hammerspoon follows the mouse

    count = len(sent(page))
    page.locator(".title").hover()  # by its title too
    page.mouse.down()
    page.mouse.up()
    page.locator("#base_url").click()  # but a box is for typing
    page.mouse.down()
    page.mouse.move(10, 10)
    page.mouse.up()
    assert [m["action"] for m in sent(page)[count:] if m["action"].startswith("drag")] == ["drag-start", "drag-end"]


def test_a_change_after_saving_is_saved_too_not_dropped_by_done(page):
    send(page, {**SETTINGS, "configured": True, "hotkeys": HOTKEYS})
    page.locator("#base_url").fill("https://openrouter.ai/api/v1")
    page.locator("#model-id").fill("openai/gpt-6-luna")
    page.keyboard.press("Enter")
    send(page, {"type": "saved", "saved": True, "ok": True, "before": "a eror", "after": "an error", "seconds": 1.0})
    assert page.locator("#primary").inner_text().startswith("Done")

    page.locator("#model-id").fill("mistralai/mistral-small-2603")  # changed your mind
    assert page.locator("#primary").inner_text().startswith("Save")
    assert "It works" not in page.locator("main").inner_text()
    assert page.locator("#model-id").evaluate("element => element === document.activeElement")  # still typing
    page.keyboard.press("Enter")
    assert sent(page)[-1]["settings"]["model"] == "mistralai/mistral-small-2603"

    send(page, {"type": "saved", "saved": True, "ok": True, "before": "a eror", "after": "an error", "seconds": 1.0})
    page.locator("#hotkey").select_option("E")  # the shortcut too
    page.locator("#primary").click()
    assert sent(page)[-1]["hotkey"] == "e"


def test_settings_offer_the_models_the_service_has_for_your_key(page):
    send(page, {**SETTINGS, "key_prefixes": KEY_PREFIXES})
    page.locator("#key").fill("gsk_abc")  # Groq: the address fills in, then Penwise asks Groq for its models
    page.wait_for_timeout(800)
    asked = [m for m in sent(page) if m.get("action") == "list-models"]
    assert asked == [
        {"action": "list-models", "settings": {"base_url": "https://api.groq.com/openai/v1", "key": "gsk_abc"}}
    ]
    send(
        page, {"type": "models", "base_url": "https://api.groq.com/openai/v1", "models": ["llama-test-8b", "qwen-test"]}
    )
    assert page.locator("#suggested-models option").count() == 2
    assert page.locator("#model-id").get_attribute("placeholder") == "Click to choose from 2 models"
    assert page.locator("#key").input_value() == "gsk_abc"  # nothing rebuilt under your fingers

    page.locator("#base_url").fill("https://openrouter.ai/api/v1")  # every service lists its own
    page.wait_for_timeout(800)
    assert len([m for m in sent(page) if m.get("action") == "list-models"]) == 2


def test_a_slow_check_says_where_a_faster_model_is(page):
    send(page, {"type": "begin", "original": "Wait untill noon.", "mode": "fix"})
    page.wait_for_timeout(400)
    assert page.locator("#slow").count() == 0  # not at once
    page.evaluate("state.checkingFrom = Date.now() - 11000")  # eleven seconds later
    page.wait_for_timeout(400)
    assert "Taking a while? A faster model helps" in page.locator("#slow").inner_text()
    page.get_by_role("button", name="Open settings").click()
    assert sent(page)[-1] == {"action": "settings"}


def test_an_error_offers_the_settings_only_when_they_can_fix_it(page):
    send(page, {"type": "begin", "original": "Hi.", "mode": "fix"})
    busy = "openrouter.ai has had too many requests (429). Wait a moment and try again."
    send(page, {"type": "error", "message": busy, "in_settings": False})
    assert busy in page.locator("main").inner_text()
    assert page.get_by_role("button", name="Open settings").count() == 0  # nothing to change there
    assert page.locator("#primary").inner_text().startswith("Try again")
    send(page, {"type": "error", "message": "The service refused the API key (401).", "in_settings": True})
    assert page.get_by_role("button", name="Open settings").count() == 1


def test_the_setup_report_can_be_copied(page):
    send(page, {"type": "note", "title": "Check my setup", "text": "Checking each part…"})
    assert page.get_by_role("button", name="Copy").count() == 0  # nothing to copy yet
    report = "✓ Penwise     0.7.15 on macOS 26.0.1\n✓ Test        fine"
    send(page, {"type": "note", "title": "Check my setup", "text": report, "copyable": True})
    page.get_by_role("button", name="Copy").click()
    assert sent(page)[-1] == {"action": "copy-text", "text": report}
    page.keyboard.press("Meta+c")
    assert sent(page)[-2:] == [{"action": "copy-text", "text": report}] * 2


def test_the_panel_says_when_ollama_is_starting(page):
    send(page, {"type": "begin", "original": "Wait untill noon.", "mode": "fix"})
    send(page, {"type": "start", "model": "gemma3:1b", "explain": False})
    send(page, {"type": "status", "text": "Starting Ollama…"})
    assert page.locator("#progress").inner_text() == "Starting Ollama…"
    page.evaluate("state.checkingFrom = Date.now() - 11000")
    page.wait_for_timeout(400)
    assert page.locator("#slow").count() == 0  # not the model's fault
    send(page, {"type": "status", "text": ""})
    assert page.locator("#progress").inner_text().startswith("Checking…")
    page.wait_for_timeout(400)
    assert page.locator("#slow").count() == 0  # the check itself has only just begun


def test_voiceover_can_undo_a_change_and_hears_whether_it_is_in(page):
    send(page, {"type": "begin", "original": "We use two dataset.", "mode": "fix"})
    send(page, check_result("We use two dataset.", "We use two datasets."))
    change = page.get_by_role("button", name="Applied: dataset → datasets")
    assert change.get_attribute("aria-pressed") == "true"
    change.click()
    undone = page.get_by_role("button", name="Not applied: dataset → datasets")
    assert undone.get_attribute("aria-pressed") == "false"
    page.keyboard.press("Enter")
    assert sent(page)[-1]["text"] == "We use two dataset."


def test_voiceover_hears_how_a_check_ended(page):
    send(page, {"type": "begin", "original": "We use two dataset.", "mode": "fix"})
    assert page.locator("#announce").inner_text() == ""  # still checking
    send(page, check_result("We use two dataset.", "We use two datasets."))
    assert page.locator("#announce").text_content() == "1 change"
    assert page.locator("#announce").get_attribute("aria-live") == "polite"
    send(page, {"type": "error", "message": "Could not reach openrouter.ai. Check your internet connection."})
    assert page.locator("#announce").text_content().startswith("Could not reach openrouter.ai")


def test_a_model_download_shows_a_progress_bar(page):
    send(page, SETTINGS)
    page.locator("#model-id").fill("gemma3:1b")
    page.locator("#primary").click()
    assert page.locator("progress").count() == 0  # "Saving and testing…": nothing to measure yet
    send(page, {"type": "saving", "text": "Downloading gemma3:1b… 40% of 815 MB"})
    assert page.locator("#saving progress").get_attribute("value") == "40"
    assert "40% of 815 MB" in page.locator("#saving").inner_text()
    send(page, {"type": "saving", "text": "Testing the model…"})
    assert page.locator("progress").count() == 0


def test_settings_take_an_endpoint_pasted_as_a_whole_request_url(page):
    send(page, SETTINGS)
    page.locator("#base_url").fill("openrouter.ai/api/v1/chat/completions")  # from a service's example
    assert page.get_by_role("button", name="Get a key").count() == 1  # a service Penwise knows
    page.locator("#base_url").fill("localhost:11434/v1/")
    assert page.locator("#key-hint").inner_text() == "Not needed for a model on your Mac."
    page.locator("#model-id").fill("m")
    page.locator("#primary").click()
    saved = {"type": "saved", "saved": True, "ok": True, "before": "a eror", "after": "an error", "seconds": 0.5}
    send(page, {**saved, "base_url": "http://localhost:11434/v1"})
    assert page.locator("#base_url").input_value() == "http://localhost:11434/v1"  # as saved


def test_settings_say_when_a_model_is_slow(page):
    send(page, {**SETTINGS, "configured": True})
    page.locator("#model-id").fill("slow-model")
    page.locator("#primary").click()
    saved = {"type": "saved", "saved": True, "ok": True, "before": "a eror", "after": "an error"}
    send(page, {**saved, "seconds": 14.2, "slow": True})
    assert "A model that doesn't think before answering is faster." in page.locator("#slow-model").inner_text()
    page.locator("#model-id").fill("another-model")  # trying another: the hint goes with the result
    assert page.locator("#slow-model").count() == 0
    send(page, {**saved, "seconds": 1.1})
    assert page.locator("#slow-model").count() == 0
