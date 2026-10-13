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
    return page.evaluate("window.sent")


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
    assert page.locator("#replace").is_disabled()
    page.get_by_role("button", name="Check my setup").click()
    assert sent(page)[-1] == {"action": "doctor"}


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
    page.keyboard.press("Enter")
    assert sent(page) == [{"action": "ready"}]  # no mode switch, nothing to replace


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
                {"label": "Articles", "count": 5, "note": "Use “an” before a vowel sound."},
                {"label": "Prepositions", "count": 2, "note": "Learn them in phrases."},
            ],
            "repeated": [{"pair": "in → on", "count": 2, "example": "results [in] the other hand"}],
        },
    )
    text = page.locator("main").inner_text()
    assert "7 changes you accepted since 2026-10-12" in text
    assert "Use “an” before a vowel sound." in text
    assert "e.g. …results [in] the other hand…" in text
    assert page.locator(".bar").count() == 2
    assert page.locator("#replace").is_hidden() and page.locator(".modes").is_hidden()
    assert page.locator("#cancel").inner_text().startswith("Close")


def test_insights_without_history(page):
    send(page, {"type": "insights", "total": 0, "since": "", "categories": [], "repeated": []})
    assert "No history yet" in page.locator("main").inner_text()
