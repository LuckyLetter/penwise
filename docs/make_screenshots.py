"""Draw the README's pictures of the panel (docs/panel-light.png, docs/panel-dark.png) from the panel
itself: a check of one sentence, with the model the README recommends.

    uv run --extra dev --with playwright python docs/make_screenshots.py
"""

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

DOCS = Path(__file__).resolve().parent
sys.path.insert(0, str(DOCS.parent / "src"))
from penwise import engine, setup_mac  # noqa: E402

MODEL = "openai/gpt-oss-20b"  # as the README recommends
BEFORE = (
    "In this paper we propose a approach that achieve better result then previous works, inspite of using less data."
)
AFTER = (
    "In this paper, we propose an approach that achieves better results than previous work, despite using less data."
)
SECONDS = 1.2  # what the footer shows the check took
WIDTH = 640


def main() -> None:
    result = engine.check(BEFORE, lambda system, messages: AFTER, model=MODEL).to_dict()
    result["elapsed_ms"] = int(SECONDS * 1000)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        for scheme in ("light", "dark"):
            page = browser.new_page(
                viewport={"width": WIDTH, "height": 400}, device_scale_factor=2, color_scheme=scheme
            )
            # What the panel sends Hammerspoon, kept: its height, to fit the picture to it.
            page.add_init_script(
                "window.sent = [];"
                "window.webkit = {messageHandlers: {penwise: {postMessage: (m) => window.sent.push(m)}}};"
            )
            page.goto(setup_mac.spoon_source().joinpath("panel.html").as_uri())
            page.add_style_tag(content="html { background: var(--bg); }")  # the corners, as in the window
            for event in (
                {"type": "begin", "original": BEFORE, "mode": "fix"},
                {"type": "start", "model": MODEL},
                result,
            ):
                page.evaluate(f"penwise.receive({json.dumps(event)})")
            height = [m["height"] for m in page.evaluate("window.sent") if m["action"] == "size"][-1]
            page.set_viewport_size({"width": WIDTH, "height": height})
            page.screenshot(path=DOCS / f"panel-{scheme}.png")
            page.close()
        browser.close()


if __name__ == "__main__":
    main()
