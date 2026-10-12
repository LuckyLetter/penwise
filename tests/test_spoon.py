"""Run the Hammerspoon Spoon in an embedded Lua with stubbed `hs` APIs (skipped without lupa).

The real `penwise` CLI runs underneath, against the fake model server.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from penwise import setup_mac

lua54 = pytest.importorskip("lupa.lua54")

STUB = Path(__file__).with_name("hs_stub.lua")
SELECTION = "Wait untill the informations arrive."


class Spoon:
    def __init__(self, delivery):
        self.lua = lua54.LuaRuntime(unpack_returned_tuples=True)
        g = self.lua.globals()
        g.SPOON_DIR = str(setup_mac.spoon_source()) + "/"
        g.SELECTION = SELECTION
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
    assert [e["type"] for e in spoon.events] == ["begin", "start", "result", "done"]
    result = spoon.events[2]
    assert result["edited"] == "Wait until the information arrive."

    changes = [{key: c[key] for key in ("before", "after", "category")} for c in result["changes"]]
    spoon.message({"action": "replace", "text": result["edited"], "changes": changes})
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
    assert spoon.events[-1]["type"] == "error"
    assert "Could not reach" in spoon.events[-1]["message"]
