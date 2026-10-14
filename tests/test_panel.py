"""Drive the review panel in a headless browser (skipped when Playwright is not installed)."""

import json

import pytest

from penwise import engine, setup_mac

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
    assert "Not applied: it would change a citation" in first.inner_text()
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
    assert page.locator("li button").count() == 0


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
    assert page.locator("footer button").count() == 1
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


def test_settings_offer_two_choices_on_this_mac_or_an_api(page):
    send(page, SETTINGS)
    assert "Welcome to Penwise" in page.locator("main").inner_text()
    choices = page.get_by_role("group", name="Where the model runs").get_by_role("button")
    assert choices.all_inner_texts() == ["On this Mac", "API"]
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
    page.get_by_role("button", name="API").click()
    page.locator("#base_url").fill("https://openrouter.ai/api/v1")  # a service Penwise knows
    page.get_by_role("button", name="Get a key").click()
    assert sent(page)[-1] == {"action": "open-url", "url": "https://openrouter.ai/settings/keys"}
    page.locator("#key").fill("sk-or-v1-abc")
    page.locator("#model-id").fill("openai/gpt-6-luna")  # suggested, but any id works
    assert page.locator("#suggested-models option").count() == 2
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
    page.locator("#primary").click()
    assert sent(page)[-1]["settings"] == {"provider": "ollama", "base_url": "", "model": "gemma3:1b", "key": ""}
    send(page, {"type": "saved", "saved": True, "ok": False, "message": "Is Ollama running?"})
    assert "Is Ollama running?" in page.locator(".error").inner_text()
    assert page.locator("#primary").inner_text().startswith("Save")  # fix it and save again


def test_settings_paste_the_key(page):
    send(page, SETTINGS)
    page.get_by_role("button", name="API").click()
    page.locator("#base_url").fill("https://api.example.com/v1")
    page.get_by_role("button", name="Paste").click()
    assert sent(page)[-1] == {"action": "paste-key"}
    send(page, {"type": "pasted", "text": " secret-key\n"})
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


def test_settings_another_local_model(page):
    send(page, SETTINGS)
    page.locator("#model-choice").select_option("other")
    page.locator("#model-id").fill("llama3.2:3b")
    page.locator("#primary").click()
    assert sent(page)[-1]["settings"]["model"] == "llama3.2:3b"


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


def test_settings_offer_the_models_already_on_this_mac_first(page):
    send(page, {**SETTINGS, "installed": ["llama3.2:1b", "qwen3:4b"]})
    choice = page.locator("#model-choice")
    assert choice.input_value() == "llama3.2:1b"  # already there: nothing to download
    assert "qwen3:4b · on your Mac" in choice.locator("option").all_inner_texts()
    page.locator("#primary").click()
    assert sent(page)[-1]["settings"]["model"] == "llama3.2:1b"

    send(page, {**SETTINGS, "configured": True, "installed": ["llama3.2:1b"]})
    assert page.locator("#model-choice").input_value() == "gemma3:1b"  # the model you chose stays


KEY_PREFIXES = [
    {"prefix": "sk-or-", "base_url": "https://openrouter.ai/api/v1"},
    {"prefix": "gsk_", "base_url": "https://api.groq.com/openai/v1"},
]


def test_settings_fill_in_the_address_that_goes_with_a_key(page):
    send(page, {**SETTINGS, "key_prefixes": KEY_PREFIXES})
    page.get_by_role("button", name="API").click()
    page.locator("#key").fill("sk-or-v1-abc")
    assert page.locator("#base_url").input_value() == "https://openrouter.ai/api/v1"
    assert page.get_by_role("button", name="Get a key").count() == 1  # and it knows the service
    assert page.locator("#suggested-models option").count() == 2

    page.locator("#base_url").fill("https://example.org/v1")  # an address you typed stays
    page.locator("#key").fill("gsk_abc")
    assert page.locator("#base_url").input_value() == "https://example.org/v1"

    page.locator("#base_url").fill("")
    send(page, {"type": "pasted", "text": "gsk_abc\n"})  # the Paste button
    assert page.locator("#base_url").input_value() == "https://api.groq.com/openai/v1"


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
