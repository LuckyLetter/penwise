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
    assert spoon.log[-4:] == [
        "hide panel",
        "focus target",
        "cmd+v: Wait until the information arrive.",
        "ran -m penwise record",
    ]
    assert spoon.lua.globals().CLIPBOARD == "user clipboard"
    assert len((config / "history.jsonl").read_text().splitlines()) == 2


def test_cancel_leaves_the_text_alone(config):
    spoon = Spoon("stream")
    spoon.run('spoon:check("fix")')
    spoon.message({"action": "ready"})
    spoon.message({"action": "cancel"})
    assert not any(line.startswith("cmd+v") for line in spoon.log)
    assert spoon.log[-1] == "focus target"


def test_errors_reach_the_panel(isolated):
    (isolated / "config.toml").write_text('base_url = "http://127.0.0.1:9/v1"\n')
    spoon = Spoon("stream")
    spoon.run('spoon:check("fix")')
    spoon.message({"action": "ready"})
    spoon.run_tasks()
    assert spoon.events[-1]["type"] == "error"
    assert "Could not reach" in spoon.events[-1]["message"]


def test_quick_fix_replaces_right_away(config):
    spoon = Spoon("stream")
    spoon.run('spoon:bindHotkeys({ quick = { { "ctrl", "alt", "cmd" }, "p" } })')
    spoon.run("HOTKEYS.quick()")
    spoon.run_tasks()
    assert spoon.events == []  # no review panel
    assert "alert Penwise: fixing…" in spoon.log
    assert "cmd+v: Wait until the information arrive." in spoon.log
    assert "alert Penwise: 2 fixes: Spelling, Uncountable noun" in spoon.log
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


def test_with_nothing_selected_a_short_field_is_checked_whole(config):
    spoon = Spoon("stream")
    field = "Wait untill noon, please."
    spoon.lua.globals().FIELD = spoon.to_lua({"AXRole": "AXTextField", "AXSelectedText": "", "AXValue": field})
    spoon.run('spoon:check("fix")')
    spoon.message({"action": "ready"})
    spoon.run_tasks()
    assert spoon.log[0] == "cmd+a: user clipboard"  # the whole field gets selected, so the paste replaces it
    assert spoon.events[0]["original"] == field


def test_with_nothing_selected_elsewhere_it_asks_for_a_selection(config):
    spoon = Spoon("stream")
    spoon.lua.globals().FIELD = spoon.to_lua({"AXRole": "AXButton", "AXSelectedText": "", "AXValue": "OK"})
    spoon.run('spoon:check("fix")')
    spoon.run_tasks()
    assert "cmd+a: user clipboard" not in spoon.log
    assert spoon.log[-1] == "alert Penwise: select some text first"
    assert spoon.lua.globals().CLIPBOARD == "user clipboard"


def test_apps_without_accessibility_text_use_copy(config):
    spoon = Spoon("stream")
    g = spoon.lua.globals()
    g.FIELD = spoon.to_lua({})
    g.COPY_RESULT = "Wait untill noon."
    spoon.run('spoon:check("fix")')
    spoon.run_tasks()  # the copy is read from a timer, like in Hammerspoon
    spoon.message({"action": "ready"})
    assert spoon.log[0] == "cmd+c: user clipboard"
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
        "Check selection    ⌃⌥P",
        "Improve selection    ⌃⌥⇧P",
        "Quick fix selection    ⌃⌥⌘P",
        "-",
        "Your recurring fixes…",
        "Change model or API key…",
        "Check my setup…",
    ]
    click(spoon, "Quick fix selection")
    spoon.run_tasks()
    assert "cmd+v: Wait until the information arrive." in spoon.log


def test_the_menu_shows_your_recurring_fixes(config):
    history.record([{"before": "in", "after": "on", "category": "preposition"}] * 2)
    spoon = Spoon("stream")
    spoon.run("spoon:start()")
    click(spoon, "Your recurring fixes")
    spoon.message({"action": "ready"})
    spoon.run_tasks()
    note = spoon.events[-1]
    assert note["type"] == "note" and note["title"] == "Your recurring fixes"
    assert "in → on" in note["text"]


def test_the_menu_opens_setup_in_terminal(config):
    spoon = Spoon("stream")
    spoon.run("spoon:start()")
    click(spoon, "Change model or API key")
    (script,) = [line for line in spoon.log if line.startswith("applescript")]
    assert 'tell application "Terminal"' in script
    assert script.rstrip().endswith('-m penwise setup"\nend tell')
