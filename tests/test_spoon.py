"""Run the Hammerspoon Spoon in an embedded Lua with stubbed `hs` APIs (skipped without lupa).

The real `penwise` CLI runs underneath, against the fake model server.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from penwise import history, setup_mac

lua54 = pytest.importorskip("lupa.lua54")

STUB = Path(__file__).with_name("hs_stub.lua")
SELECTION = "Wait untill the informations arrive."


class Spoon:
    def __init__(self, delivery):
        self.lua = lua54.LuaRuntime(unpack_returned_tuples=True)
        g = self.lua.globals()
        g.SPOON_DIR = str(setup_mac.spoon_source()) + "/"
        g.FIELD = self.to_lua({"AXRole": "AXTextArea", "AXSelectedText": SELECTION, "AXValue": SELECTION})
        g.DELIVERY = delivery
        g.json_encode = lambda table: json.dumps(self.to_python(table))
        g.json_decode = lambda text: self.to_lua(json.loads(text))
        g.run_command = self.run_command
        self.lua.execute(STUB.read_text())
        spoon = self.lua.eval('dofile(SPOON_DIR .. "init.lua")')
        spoon.bin = sys.executable
        spoon.args = self.to_lua(["-m", "penwise"])
        spoon.checkForUpdates = False  # tests don't look for updates online
        g.spoon = spoon.init(spoon)

    def run_command(self, path, args, stdin):
        proc = subprocess.run([path, *self.to_python(args)], input=stdin, capture_output=True, text=True)
        return proc.stdout, proc.stderr, proc.returncode

    def to_python(self, value):
        if lua54.lua_type(value) != "table":
            return value
        keys = list(value.keys())
        if keys and all(isinstance(k, int) for k in keys):
            return [self.to_python(value[k]) for k in sorted(keys)]
        return {k: self.to_python(value[k]) for k in keys}

    def to_lua(self, value):
        if isinstance(value, dict):
            return self.lua.table_from({k: self.to_lua(v) for k, v in value.items()})
        if isinstance(value, list):
            return self.lua.table_from([self.to_lua(v) for v in value])
        return value

    def run(self, code):
        return self.lua.execute(code)

    def run_tasks(self):
        self.run("run_tasks()")

    def message(self, body):
        self.lua.globals().MESSAGE_BODY = self.to_lua(body)
        self.run("SEND_MESSAGE({ body = MESSAGE_BODY })")

    @property
    def events(self):
        prefix = "penwise.receive("
        return [json.loads(js[len(prefix) : -1]) for js in self.lua.globals().JS.values()]

    @property
    def log(self):
        return list(self.lua.globals().LOG.values())


@pytest.fixture
def config(server, isolated):
    (isolated / "config.toml").write_text(f'base_url = "{server.url}"\n')
    return isolated


@pytest.mark.parametrize("delivery", ["stream", "final"])
def test_hotkey_check_and_replace(config, delivery):
    spoon = Spoon(delivery)
    spoon.run('spoon:bindHotkeys({ fix = { { "ctrl", "alt" }, "p" } })')
    spoon.run("HOTKEYS.fix()")
    assert spoon.events == []  # held back until the panel has loaded

    spoon.message({"action": "ready"})
    spoon.run_tasks()
    assert [e["type"] for e in spoon.events] == ["begin", "start", "result", "done"]
    result = spoon.events[2]
    assert result["edited"] == "Wait until the information arrive."

    changes = [{key: c[key] for key in ("before", "after", "category")} for c in result["changes"]]
    spoon.message({"action": "replace", "text": result["edited"], "changes": changes})
    spoon.run_tasks()
    assert spoon.log[-4:-1] == ["hide panel", "focus target", "cmd+v: Wait until the information arrive."]
    assert spoon.log[-1].startswith("ran -m penwise record -- ")
    assert spoon.lua.globals().CLIPBOARD == "user clipboard"
    assert len((config / "history.jsonl").read_text().splitlines()) == 2


def test_cancel_leaves_the_text_alone(config):
    spoon = Spoon("stream")
    spoon.run('spoon:check("fix")')
    spoon.message({"action": "ready"})
    spoon.message({"action": "cancel"})
    assert not any(line.startswith("cmd+v") for line in spoon.log)
    assert spoon.log[-1] == "focus target"


def test_errors_reach_the_panel_and_can_be_retried(server, isolated):
    (isolated / "config.toml").write_text('base_url = "http://127.0.0.1:9/v1"\n')
    spoon = Spoon("stream")
    spoon.run('spoon:check("fix")')
    spoon.message({"action": "ready"})
    spoon.run_tasks()
    assert spoon.events[-1]["type"] == "error"
    assert "Could not reach" in spoon.events[-1]["message"]

    (isolated / "config.toml").write_text(f'base_url = "{server.url}"\n')  # back online
    spoon.message({"action": "retry", "mode": "fix"})
    spoon.run_tasks()
    assert spoon.events[-1]["type"] == "done"
    assert spoon.events[-2]["edited"] == "Wait until the information arrive."


def test_quick_fix_replaces_right_away(config):
    spoon = Spoon("stream")
    spoon.run('spoon:bindHotkeys({ quick = { { "ctrl", "alt", "cmd" }, "p" } })')
    spoon.run("HOTKEYS.quick()")
    spoon.run_tasks()
    assert spoon.events == []  # no review panel
    assert "alert Penwise: fixing…" in spoon.log
    assert "cmd+v: Wait until the information arrive." in spoon.log
    assert "alert Penwise: 2 fixes: Spelling, Uncountable noun  (⌘Z to undo)" in spoon.log
    assert any("--no-explain" in line for line in spoon.log)
    spoon.run_tasks()  # the history update
    assert len((config / "history.jsonl").read_text().splitlines()) == 2
    assert spoon.lua.globals().CLIPBOARD == "user clipboard"


def test_quick_fix_says_when_there_is_nothing_to_fix(config):
    spoon = Spoon("stream")
    spoon.lua.globals().FIELD = spoon.to_lua({"AXRole": "AXTextArea", "AXSelectedText": "All good here."})
    spoon.run("spoon:quickFix()")
    spoon.run_tasks()
    assert "alert Penwise: looks good, nothing to fix" in spoon.log
    assert not any(line.startswith("cmd+v") for line in spoon.log)


FIELD_TEXT = "Wait untill noon, please."


def check_whole_field(spoon, **app):
    """Check a text field with nothing selected, then press Replace."""
    spoon.lua.globals().FIELD = spoon.to_lua(
        {"AXRole": "AXTextField", "AXSelectedText": "", "AXValue": FIELD_TEXT, **app}
    )
    spoon.run('spoon:check("fix")')
    spoon.message({"action": "ready"})
    spoon.run_tasks()
    assert spoon.events[0]["original"] == FIELD_TEXT
    assert not any(line.startswith("cmd+") for line in spoon.log)  # nothing selected while you review
    spoon.message({"action": "replace", "text": "Wait until noon, please.", "changes": []})
    spoon.run_tasks()


def test_with_nothing_selected_a_short_field_is_checked_whole_and_replaced(config):
    spoon = Spoon("stream")
    check_whole_field(spoon)
    # Selected with ⌘A right before the paste, so the fix replaces the text instead of joining it.
    assert spoon.log[-2:] == ["cmd+a: user clipboard", "cmd+v: Wait until noon, please."]


def test_chrome_and_electron_apps_show_the_selection_a_moment_later(config):
    spoon = Spoon("stream")
    check_whole_field(spoon, SELECTION_LAG=4)
    assert spoon.log[-2:] == ["cmd+a: user clipboard", "cmd+v: Wait until noon, please."]


def test_when_cmd_a_doesnt_select_accessibility_does(config):
    spoon = Spoon("stream")
    check_whole_field(spoon, IGNORES_SELECT_ALL=True)
    selected = spoon.lua.globals().FIELD.AXSelectedTextRange
    assert (selected.location, selected.length) == (0, len(FIELD_TEXT))
    assert spoon.log[-1] == "cmd+v: Wait until noon, please."


def test_when_the_text_cant_be_selected_the_fix_is_copied_not_pasted_next_to_it(config):
    spoon = Spoon("stream")
    check_whole_field(spoon, IGNORES_AX_SELECTION=True, IGNORES_SELECT_ALL=True)
    assert not any(line.startswith("cmd+v") for line in spoon.log)
    assert spoon.log[-1].startswith("alert Penwise: couldn't select your text")
    assert spoon.lua.globals().CLIPBOARD == "Wait until noon, please."


def test_when_the_app_doesnt_come_back_the_fix_is_copied(config):
    spoon = Spoon("stream")
    spoon.run('spoon:check("fix")')
    spoon.message({"action": "ready"})
    spoon.run_tasks()
    spoon.lua.globals().FRONT_APP = "org.hammerspoon.Hammerspoon"  # the app never returns to the front
    spoon.message({"action": "replace", "text": "Wait until the information arrive.", "changes": []})
    spoon.run_tasks()
    assert not any(line.startswith("cmd+v") for line in spoon.log)
    assert spoon.log[-1].startswith("alert Penwise: couldn't select your text")


def test_with_nothing_selected_elsewhere_it_asks_for_a_selection(config):
    spoon = Spoon("stream")
    spoon.lua.globals().FIELD = spoon.to_lua({"AXRole": "AXButton", "AXSelectedText": "", "AXValue": "OK"})
    spoon.run('spoon:check("fix")')
    spoon.run_tasks()
    assert "cmd+a: user clipboard" not in spoon.log
    assert spoon.log[-1] == "alert Penwise: click in a text box, or select the text to check"
    assert spoon.lua.globals().CLIPBOARD == "user clipboard"


def test_without_accessibility_permission_it_says_how_to_turn_it_on(config):
    spoon = Spoon("stream")
    spoon.lua.globals().ACCESSIBILITY = False
    spoon.run('spoon:check("fix")')
    assert spoon.log == ["alert Penwise: turn on Hammerspoon in System Settings → Privacy & Security → Accessibility"]


def test_apps_without_accessibility_text_use_copy(config):
    spoon = Spoon("stream")
    g = spoon.lua.globals()
    g.FIELD = spoon.to_lua({})
    g.COPY_RESULT = "Wait untill noon."
    spoon.run('spoon:check("fix")')
    spoon.run_tasks()  # the copy is read from a timer, like in Hammerspoon
    spoon.message({"action": "ready"})
    # Electron apps (Slack, Teams, ...) are asked to show their text, for next time.
    assert spoon.log[:2] == ["app AXManualAccessibility = true", "cmd+c: user clipboard"]
    assert spoon.events[0]["original"] == "Wait untill noon."
    assert g.CLIPBOARD == "user clipboard"  # put back right after copying


def menu_items(spoon):
    items = spoon.lua.eval("MENU()")
    return [items[i] for i in range(1, len(items) + 1)]


def click(spoon, title):
    item = next(item for item in menu_items(spoon) if item["title"].startswith(title))
    item["fn"]()


def test_the_menu_bar_offers_every_action_with_its_hotkey(config):
    spoon = Spoon("stream")
    spoon.run(
        'spoon:bindHotkeys({ fix = { { "ctrl", "alt" }, "p" }, improve = { { "ctrl", "alt", "shift" }, "p" },'
        ' quick = { { "ctrl", "alt", "cmd" }, "p" } }); spoon:start()'
    )
    assert spoon.lua.globals().MENU_TITLE == "✎"
    assert [item["title"] for item in menu_items(spoon)] == [
        "Check text    ⌃⌥P",
        "Improve text    ⌃⌥⇧P",
        "Quick fix    ⌃⌥⌘P",
        "-",
        "Your recurring fixes…",
        "Try it on a practice note",
        "Settings…",
        "Check my setup…",
    ]
    click(spoon, "Quick fix")
    spoon.run_tasks()
    assert "cmd+v: Wait until the information arrive." in spoon.log


def test_the_menu_shows_your_recurring_fixes(config):
    history.record([{"before": "in", "after": "on", "category": "preposition"}] * 2)
    spoon = Spoon("stream")
    spoon.run("spoon:start()")
    click(spoon, "Your recurring fixes")
    spoon.message({"action": "ready"})
    spoon.run_tasks()
    insights = spoon.events[-1]
    assert insights["type"] == "insights" and insights["total"] == 2
    assert insights["repeated"][0]["pair"] == "in → on"


def test_the_menu_opens_setup_in_terminal(config):
    spoon = Spoon("stream")
    spoon.run("spoon:start()")
    click(spoon, "Settings")
    (script,) = [line for line in spoon.log if line.startswith("applescript")]
    assert 'tell application "Terminal"' in script
    assert script.rstrip().endswith('-m penwise setup"\nend tell')


def test_an_error_offers_to_check_the_setup(isolated):
    (isolated / "config.toml").write_text('base_url = "http://127.0.0.1:9/v1"\n')
    spoon = Spoon("stream")
    spoon.run('spoon:check("fix")')
    spoon.message({"action": "ready"})
    spoon.run_tasks()
    assert spoon.events[-1]["type"] == "error"
    spoon.message({"action": "doctor"})
    assert any(line.startswith("applescript") and "doctor" in line for line in spoon.log)


def test_quick_fix_leaves_risky_changes_for_review(config):
    spoon = Spoon("stream")
    spoon.lua.globals().FIELD = spoon.to_lua({"AXRole": "AXTextArea", "AXSelectedText": "Wait untill noon [3]."})
    spoon.run("spoon:quickFix()")
    spoon.run_tasks()
    assert "cmd+v: Wait until noon [3]." in spoon.log
    assert "alert Penwise: 1 fix: Spelling  (⌘Z to undo)  · 1 left for you to review (⌃⌥P)" in spoon.log
    spoon.run_tasks()
    assert len((config / "history.jsonl").read_text().splitlines()) == 1  # only the applied fix


def test_keeping_a_word_saves_it(config):
    spoon = Spoon("stream")
    spoon.run('spoon:check("fix")')
    spoon.message({"action": "ready"})
    spoon.message({"action": "keep", "word": "Pytorch"})
    spoon.run_tasks()
    assert "ran -m penwise keep -- Pytorch" in spoon.log
    assert 'keep = ["Pytorch"]' in (config / "config.toml").read_text()


def test_the_menu_offers_an_update_when_there_is_one(config, tmp_path):
    fake = tmp_path / "penwise"
    fake.write_text('#!/bin/sh\necho \'{"available": true, "detail": "2 new changes"}\'\n')
    fake.chmod(0o755)
    spoon = Spoon("stream")
    spoon.lua.globals().spoon.bin = str(fake)
    spoon.lua.globals().spoon.args = spoon.to_lua([])
    spoon.run("spoon.checkForUpdates = true; spoon:start()")
    spoon.run_tasks()
    assert spoon.lua.globals().MENU_TITLE == "✎•"
    assert menu_items(spoon)[0]["title"] == "Update Penwise (2 new changes)…"
    click(spoon, "Update Penwise")
    assert any(line.startswith("applescript") and "update" in line for line in spoon.log)


def test_the_app_sets_the_tone(config):
    spoon = Spoon("stream")
    g = spoon.lua.globals()
    g.APP_ID, g.WINDOW_TITLE = "com.google.Chrome", "Inbox - Gmail"
    spoon.run('spoon:check("improve")')
    spoon.message({"action": "ready"})
    spoon.run_tasks()
    assert any("--app com.google.Chrome --window Inbox - Gmail" in line for line in spoon.log)
    assert spoon.events[1]["style"] == "email"

    spoon.message({"action": "style", "style": "chat"})  # chosen in the panel
    spoon.run_tasks()
    assert spoon.events[-3]["style"] == "chat"
    assert "--style chat" in spoon.log[-1]


def panel_frame(spoon):
    frame = spoon.lua.globals().PANEL.frame
    return {key: frame[key] for key in ("x", "y", "w", "h")}


def test_the_panel_opens_above_the_text_field_and_fits_its_content(config):
    spoon = Spoon("stream")
    field = {"x": 100, "y": 800}, {"w": 600, "h": 40}
    spoon.lua.globals().FIELD = spoon.to_lua(
        {"AXRole": "AXTextArea", "AXSelectedText": "", "AXValue": SELECTION, "AXPosition": field[0], "AXSize": field[1]}
    )
    spoon.run('spoon:check("fix")')
    assert panel_frame(spoon) == {"x": 100, "y": 800 - 8 - 240, "w": 600, "h": 240}

    # The panel's content needs 300 points; the window adds a 28-point title bar.
    spoon.message({"action": "size", "height": 300, "viewport": 240 - 28})
    assert panel_frame(spoon) == {"x": 100, "y": 800 - 8 - 328, "w": 600, "h": 328}  # still just above


def test_the_panel_opens_below_a_field_at_the_top_of_the_screen(config):
    spoon = Spoon("stream")
    spoon.lua.globals().FIELD = spoon.to_lua(
        {
            "AXRole": "AXTextField",
            "AXSelectedText": SELECTION,
            "AXPosition": {"x": 1200, "y": 30},
            "AXSize": {"w": 200, "h": 22},
        }
    )
    spoon.run('spoon:check("fix")')
    assert panel_frame(spoon) == {"x": 1440 - 480 - 8, "y": 30 + 22 + 8, "w": 480, "h": 240}


def test_in_a_document_the_panel_opens_at_the_selection(config):
    spoon = Spoon("stream")
    spoon.lua.globals().FIELD = spoon.to_lua(
        {
            "AXRole": "AXTextArea",
            "AXSelectedText": SELECTION,
            "AXSelectedTextRange": {"location": 50, "length": len(SELECTION)},
            "AXPosition": {"x": 0, "y": 0},
            "AXSize": {"w": 1000, "h": 880},
            "BOUNDS": {"x": 300, "y": 400, "w": 250, "h": 20},
        }
    )
    spoon.run('spoon:check("fix")')
    assert panel_frame(spoon) == {"x": 300, "y": 400 - 8 - 240, "w": 480, "h": 240}


def utf16(text):
    return len(text.encode("utf-16-le")) // 2


def check_at_cursor(spoon, value, cursor):
    spoon.lua.globals().FIELD = spoon.to_lua(
        {
            "AXRole": "AXTextArea",
            "AXSelectedText": "",
            "AXValue": value,
            "AXSelectedTextRange": {"location": utf16(value[:cursor]), "length": 0},
        }
    )
    spoon.run('spoon:check("fix")')
    spoon.message({"action": "ready"})
    original = spoon.events[0]["original"]
    spoon.message({"action": "replace", "text": original.replace("have", "has"), "changes": []})
    spoon.run_tasks()
    selected = spoon.lua.globals().FIELD.AXSelectedTextRange
    return original, (selected.location, selected.length)


def test_with_nothing_selected_in_a_long_field_the_paragraph_at_the_cursor_is_checked(config):
    spoon = Spoon("stream")
    spoon.run("spoon.wholeFieldLimit = 60")
    paragraph = "Second 😀 paragraph have a eror.\nIt continue here."
    value = f"First paragraph is fine.\n\n{paragraph}\n\n  Third one, which is also fine."
    original, selected = check_at_cursor(spoon, value, value.index("paragraph have"))
    assert original == paragraph
    # Selected when replacing (in UTF-16 units, like macOS counts), so the fix goes in its place.
    assert selected == (utf16(value[: value.index(paragraph)]), utf16(paragraph))
    assert [line for line in spoon.log if line.startswith("cmd+")] == ["cmd+v: " + paragraph.replace("have", "has")]


def test_without_blank_lines_the_line_at_the_cursor_is_checked(config):
    spoon = Spoon("stream")
    spoon.run("spoon.wholeFieldLimit = 30")
    value = "Line one is here.\nLine two have a eror.\nLine three."
    original, _ = check_at_cursor(spoon, value, value.index("eror") + 4)  # at the end of the line
    assert original == "Line two have a eror."


def test_the_panel_shows_on_every_space_and_over_full_screen_apps(config):
    spoon = Spoon("stream")
    spoon.run('spoon:check("fix")')
    assert spoon.lua.globals().PANEL.behavior == 1 | 256  # canJoinAllSpaces, fullScreenAuxiliary


def test_clicking_elsewhere_closes_the_panel(config):
    spoon = Spoon("stream")
    spoon.run('spoon:check("fix")')
    spoon.message({"action": "ready"})
    spoon.run('WINDOW_CALLBACK("focusChange", nil, false)')
    assert spoon.log[-1] == "hide panel"  # and focus stays where you clicked
    assert not spoon.lua.globals().PANEL.visible


def test_the_hotkey_in_another_app_checks_that_apps_text(config):
    spoon = Spoon("stream")
    spoon.run('spoon:check("fix")')
    spoon.message({"action": "ready"})
    spoon.lua.globals().FIELD = spoon.to_lua({"AXRole": "AXTextArea", "AXSelectedText": "Other text have a eror."})
    spoon.run('spoon:check("fix")')  # the panel is still open, but you're in an app
    assert spoon.events[-1] == {"type": "begin", "original": "Other text have a eror.", "mode": "fix"}

    spoon.lua.globals().FRONT_APP = "org.hammerspoon.Hammerspoon"  # in the panel: switch the mode
    spoon.run('spoon:check("improve")')
    assert spoon.events[-1] == {"type": "begin", "original": "Other text have a eror.", "mode": "improve"}


def test_quick_fix_does_nothing_while_the_panel_is_in_front(config):
    spoon = Spoon("stream")
    spoon.lua.globals().FRONT_APP = "org.hammerspoon.Hammerspoon"
    spoon.run("spoon:quickFix()")
    spoon.run_tasks()
    assert spoon.log == []


TERMINAL_TEXT = "me@mac ~ % penwise history\nHistory: ~/.config/penwise/history.jsonl\nme@mac ~ % "


def test_a_terminal_is_never_read_whole(config):
    spoon = Spoon("stream")
    g = spoon.lua.globals()
    g.APP_ID = "com.apple.Terminal"
    g.FIELD = spoon.to_lua({"AXRole": "AXTextArea", "AXSelectedText": "", "AXValue": TERMINAL_TEXT})
    spoon.run('spoon:check("fix")')
    spoon.run_tasks()
    assert spoon.events == []  # the commands and output above the prompt are not your text
    assert spoon.log[-1] == "alert Penwise: in a terminal, select the text to check first"


def test_in_a_terminal_replace_clears_the_line_you_are_typing_and_pastes_the_fix(config):
    spoon = Spoon("stream")
    g = spoon.lua.globals()
    g.APP_ID = "com.apple.Terminal"
    g.FIELD = spoon.to_lua({"AXRole": "AXTextArea", "AXSelectedText": SELECTION, "AXValue": TERMINAL_TEXT})
    spoon.run('spoon:check("fix")')
    spoon.message({"action": "ready"})
    spoon.run_tasks()
    assert "readonly" not in spoon.events[0]  # the button says Replace
    spoon.message({"action": "replace", "text": "Wait until the information arrive.", "changes": []})
    spoon.run_tasks()
    assert spoon.log[-3:] == [
        "ctrl+e: user clipboard",  # end of the line
        "ctrl+u: user clipboard",  # clear it
        "cmd+v: Wait until the information arrive.",
    ]


def test_in_a_terminal_only_what_you_typed_is_checked(config):
    spoon = Spoon("stream")
    g = spoon.lua.globals()
    g.APP_ID = "com.googlecode.iterm2"
    claude_code_box = "\n".join(
        [
            "╭────────────────────────────╮",
            "│ > Wait untill the informations   │",
            "│   arrive.                  │",
            "╰────────────────────────────╯",
        ]
    )
    g.FIELD = spoon.to_lua({"AXRole": "AXTextArea", "AXSelectedText": claude_code_box})
    spoon.run('spoon:check("fix")')
    spoon.message({"action": "ready"})
    assert spoon.events[0]["original"] == "Wait untill the informations arrive."


def test_copy_waits_until_you_let_go_of_the_hotkey(config):
    spoon = Spoon("stream")
    g = spoon.lua.globals()
    g.FIELD = spoon.to_lua({})
    g.COPY_RESULT = "Wait untill noon."
    g.HELD_KEYS = 5  # ⌃⌥ still down for a moment: ⌘C now would arrive as ⌃⌥⌘C
    spoon.run('spoon:check("fix")')
    spoon.run_tasks()
    spoon.message({"action": "ready"})
    assert g.KEY_CHECKS > 5
    assert spoon.events[0]["original"] == "Wait untill noon."


def test_chrome_is_asked_to_build_its_accessibility_tree(config):
    spoon = Spoon("stream")
    g = spoon.lua.globals()
    g.APP_ID = "com.google.Chrome"
    g.FIELD = spoon.to_lua({})
    g.ELECTRON_FIELD = spoon.to_lua({"AXRole": "AXTextArea", "AXSelectedText": "", "AXValue": "Wait untill noon."})
    spoon.run('spoon:check("fix")')
    spoon.message({"action": "ready"})
    assert "app AXEnhancedUserInterface = true" in spoon.log
    assert spoon.events[0]["original"] == "Wait untill noon."


def test_text_selected_on_a_web_page_is_copied_not_replaced(config):
    spoon = Spoon("stream")
    spoon.lua.globals().FIELD = spoon.to_lua({"AXRole": "AXWebArea", "AXSelectedText": SELECTION, "READONLY": True})
    spoon.run('spoon:check("fix")')
    spoon.message({"action": "ready"})
    assert spoon.events[0]["readonly"] is True


def test_a_text_box_counts_as_editable_whatever_the_app_says(config):
    spoon = Spoon("stream")
    spoon.lua.globals().FIELD = spoon.to_lua(
        {"AXRole": "AXTextArea", "AXSelectedText": "", "AXValue": "Wait untill noon.", "READONLY": True}
    )
    spoon.run('spoon:check("fix")')
    spoon.message({"action": "ready"})
    assert spoon.events[0] == {"type": "begin", "original": "Wait untill noon.", "mode": "fix"}  # rich-text boxes


def test_over_a_full_screen_app_the_panel_doesnt_bring_hammerspoon_forward(config):
    spoon = Spoon("stream")
    spoon.lua.globals().FULL_SCREEN = True
    spoon.run('spoon:check("fix")')
    assert spoon.lua.globals().PANEL.style == 0 | 128  # borderless, nonactivating
    assert "activate Hammerspoon" not in spoon.log  # that would switch to the desktop

    spoon.lua.globals().FULL_SCREEN = False
    spoon.run('spoon:check("fix")')
    assert "activate Hammerspoon" in spoon.log


def test_electron_apps_are_asked_to_show_their_text_and_read_right_away(config):
    spoon = Spoon("stream")
    g = spoon.lua.globals()
    g.FIELD = spoon.to_lua({})  # Claude, Slack, ...: nothing to read until asked
    g.ELECTRON_FIELD = spoon.to_lua({"AXRole": "AXTextArea", "AXSelectedText": "", "AXValue": "Wait untill noon."})
    spoon.run('spoon:check("fix")')
    spoon.message({"action": "ready"})
    spoon.run_tasks()
    assert "app AXManualAccessibility = true" in spoon.log
    assert spoon.events[0]["original"] == "Wait untill noon."
    assert not any(line.startswith("cmd+c") for line in spoon.log)


def test_the_hotkey_in_a_focused_panel_switches_the_mode(config):
    spoon = Spoon("stream")
    spoon.run('spoon:check("fix")')
    spoon.message({"action": "ready"})
    spoon.run('WINDOW_CALLBACK("focusChange", nil, true)')  # the panel has the keyboard; the app stays in front
    spoon.run('spoon:check("improve")')
    assert spoon.events[-1] == {"type": "begin", "original": SELECTION, "mode": "improve"}


def test_the_log_says_what_happened_without_your_text(config, tmp_path):
    spoon = Spoon("stream")
    log_file = tmp_path / "hotkey.log"
    spoon.lua.globals().spoon.logFile = str(log_file)
    check_whole_field(spoon)
    log = log_file.read_text()
    for step in [
        "hotkey in com.apple.TextEdit",
        "read: whole text box, AXTextField, field, 25 characters",
        "panel shown",
        "replace: field",
        "back in the app",
        "selected the text (⌘A), pasted the fix",
    ]:
        assert step in log
    assert "untill" not in log and "until" not in log
