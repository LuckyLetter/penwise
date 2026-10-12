"""Integration tests that need a real Mac. CI runs them on a macOS runner.

They use the real Keychain and the real Hammerspoon app, so they only run when
PENWISE_MACOS_INTEGRATION=1 is set. The Hammerspoon test writes to
~/.config/penwise and ~/.hammerspoon: run it only on a throwaway machine.
"""

import os
import platform
import subprocess
import time

import pytest

from penwise import config, keychain, setup_mac
from penwise.config import Config

pytestmark = pytest.mark.skipif(
    platform.system() != "Darwin" or os.environ.get("PENWISE_MACOS_INTEGRATION") != "1",
    reason="needs a real Mac and PENWISE_MACOS_INTEGRATION=1",
)

HS = "/Applications/Hammerspoon.app/Contents/Frameworks/hs/hs"


def test_keychain_round_trip(monkeypatch):
    service = f"penwise-test-{os.getpid()}"
    monkeypatch.setattr(keychain, "SERVICE", service)
    try:
        assert keychain._save_through_stdin("sk-or-v1-first"), "security -i did not store the key"
        assert keychain.read() == "sk-or-v1-first"
        keychain.save("sk-or-v1-second")  # replaces the saved key
        assert keychain.read() == "sk-or-v1-second"
        command = f"security find-generic-password -s {service} -w"
        assert Config(api_key_command=command).resolve_api_key() == "sk-or-v1-second"
    finally:
        subprocess.run(["security", "delete-generic-password", "-s", service], capture_output=True)


def hs(lua: str, timeout: float = 10) -> str:
    """Run Lua inside Hammerspoon and return the last line it printed."""
    out = subprocess.run([HS, "-c", lua], capture_output=True, text=True, timeout=timeout)
    lines = [line for line in out.stdout.splitlines() if line.strip()]
    return lines[-1].strip() if lines else ""


def wait_for(lua: str, done, seconds: float = 60) -> str:
    deadline = time.monotonic() + seconds
    value = ""
    while time.monotonic() < deadline:
        try:
            value = hs(lua)
        except subprocess.TimeoutExpired:
            value = ""
        if done(value):
            return value
        time.sleep(1)
    console = subprocess.run([HS, "-c", "return hs.console.getConsole()"], capture_output=True, text=True).stdout
    pytest.fail(f"Timed out waiting for {lua!r}; last value {value!r}\nHammerspoon console:\n{console}")


@pytest.fixture
def hammerspoon(server):
    if not setup_mac.hammerspoon_installed():
        pytest.skip("Hammerspoon is not installed")
    config.write_config({"base_url": server.url, "model": "test-model"})
    setup_mac.install_spoon()
    init_file = setup_mac.hammerspoon_dir() / "init.lua"
    init_file.write_text('require("hs.ipc")\n')
    setup_mac.write_snippet(init_file)
    subprocess.run(["open", "-a", "Hammerspoon"], check=True)
    wait_for("return tostring(spoon and spoon.Penwise ~= nil)", lambda v: v == "true")
    yield
    subprocess.run(["osascript", "-e", 'quit app "Hammerspoon"'], capture_output=True)


def test_review_panel_and_quick_fix_in_real_hammerspoon(hammerspoon):
    assert hs("return tostring(spoon.Penwise.menu ~= nil)") == "true"  # the ✎ menu bar icon

    # The review panel: the page loads, says it is ready, and shows the result.
    hs('spoon.Penwise:_showPanel(); spoon.Penwise:_review("This have a error.", "fix"); return "ok"')
    wait_for("return tostring(spoon.Penwise.ready)", lambda v: v == "true")
    panel = wait_for(
        'spoon.Penwise.webview:evaluateJavaScript("JSON.stringify([state.status, finalText()])",'
        " function(result) PANEL = result end); return tostring(PANEL)",
        lambda v: '"ready"' in v,
    )
    assert panel == '["ready","This has an error."]'

    # The quick fix: the result arrives through hs.task, with the text passed as an argument.
    hs(
        'QUICK = nil; spoon.Penwise:_run("Wait untill noon.", "fix", { "--no-explain" },'
        ' function(event) if event.type == "result" then QUICK = event.edited end end); return "ok"'
    )
    assert wait_for("return tostring(QUICK)", lambda v: v not in ("", "nil")) == "Wait until noon."
    console = subprocess.run([HS, "-c", "return hs.console.getConsole()"], capture_output=True, text=True).stdout
    assert "stack traceback" not in console, console
