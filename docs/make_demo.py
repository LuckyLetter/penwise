"""Draw the README's animation (docs/demo.gif): a sentence in a text box, ⌃⌥P, the panel's Fix,
Tab for Improve, Return, and the text replaced. About five seconds, looping.

The panel is the real one (panel.html, with what `penwise check` sends it), over a plain text box.

    uv run --extra dev --with playwright --with pillow python docs/make_demo.py
"""

import io
import json
import sys
import tempfile
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

DOCS = Path(__file__).resolve().parent
sys.path.insert(0, str(DOCS.parent / "src"))
from penwise import engine, setup_mac  # noqa: E402

MODEL = "openai/gpt-oss-20b"  # as the README recommends
ORIGINAL = "We evaluate our method on three benchmark and it outperform previous work."
FIXED = "We evaluate our method on three benchmarks, and it outperforms previous work."
IMPROVED = "We evaluate our method on three benchmarks, where it clearly outperforms previous work."
WIDTH, SCALE = 720, 2
PANEL = {"left": 60, "top": 150, "width": 600}  # under the text, as Penwise puts it

STAGE = """<!doctype html><meta charset="utf-8">
<style>
  body { margin: 0; width: %(width)dpx; height: 100vh; overflow: hidden;
    background: #e8ecf2; font: 15px/1.5 -apple-system, sans-serif; }
  .window { position: absolute; left: 30px; top: 26px; right: 30px; height: 250px; background: #fff;
    border-radius: 12px; box-shadow: 0 10px 30px rgb(0 0 0 / 0.12), 0 0 0 1px rgb(0 0 0 / 0.06); }
  .bar { height: 38px; border-bottom: 1px solid #ececf0; display: flex; align-items: center; gap: 8px;
    padding: 0 14px; }
  .bar i { width: 12px; height: 12px; border-radius: 50%%; background: #e3e3e8; }
  .text { margin: 12px 14px; padding: 10px 12px; font-size: 17px; line-height: 1.6; color: #1d1d1f;
    border-radius: 6px; }
  .text.done { background: #e6f4ea; }
  .caret { display: inline-block; width: 2px; height: 1.1em; vertical-align: text-bottom; background: #2f6fde; }
  iframe { position: absolute; left: %(left)dpx; top: %(top)dpx; width: %(panel)dpx; height: 400px; border: 0;
    border-radius: 12px; box-shadow: 0 18px 50px rgb(0 0 0 / 0.2); background: transparent; visibility: hidden; }
  .key { position: absolute; right: 46px; top: 31px; padding: 2px 12px; border-radius: 7px; display: none;
    background: #1d1d1f; color: #fff; font-size: 16px; font-weight: 600; letter-spacing: 0.04em; }
</style>
<div class="window"><div class="bar"><i></i><i></i><i></i></div><div class="text" id="text"></div></div>
<iframe id="panel" src="%(src)s"></iframe>
<div class="key" id="key"></div>
"""


def events(mode: str, edited: str) -> list[dict]:
    """What `penwise check` sends the panel for one check: begin and start, then the result."""
    result = engine.check(ORIGINAL, lambda system, messages: edited, mode=mode, model=MODEL).to_dict()
    result["elapsed_ms"] = 1200
    return [
        {"type": "begin", "original": ORIGINAL, "mode": mode},
        {"type": "start", "model": MODEL, "style": "academic"},
        result,
    ]


def main() -> None:
    fix, improve = events("fix", FIXED), events("improve", IMPROVED)
    frames: list[tuple[Image.Image, int]] = []
    with tempfile.TemporaryDirectory() as folder, sync_playwright() as playwright:
        stage = Path(folder) / "stage.html"
        source = setup_mac.spoon_source().joinpath("panel.html").as_uri()
        stage.write_text(STAGE % {"width": WIDTH, "src": source, "panel": PANEL["width"], **PANEL}, encoding="utf-8")
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": WIDTH, "height": 900}, device_scale_factor=SCALE)
        # The panel's messages to Hammerspoon, kept: its height, to size it as the window is.
        page.add_init_script(
            "window.sent = [];window.webkit = {messageHandlers: {penwise: {postMessage: (m) => window.sent.push(m)}}};"
        )
        page.goto(stage.as_uri())
        panel = next(frame for frame in page.frames if frame.url.endswith("panel.html"))

        def run(script: str, argument: object = None) -> None:
            page.evaluate(script, argument)

        def text(value: str, done: bool = False) -> None:
            run(
                "([value, done]) => { const box = document.getElementById('text'); box.replaceChildren(value);"
                " box.className = done ? 'text done' : 'text';"
                " if (!done) box.append(Object.assign(document.createElement('span'), { className: 'caret' })); }",
                [value, done],
            )

        def key(label: str = "") -> None:
            run(
                "(label) => { const key = document.getElementById('key'); key.textContent = label;"
                " key.style.display = label ? 'block' : 'none'; }",
                label,
            )

        def show(event_list: list[dict]) -> int:
            for event in event_list:
                panel.evaluate(f"penwise.receive({json.dumps(event)})")
            height = [m["height"] for m in panel.evaluate("window.sent") if m["action"] == "size"][-1]
            run(
                "(height) => { const frame = document.getElementById('panel');"
                " frame.style.height = height + 'px'; frame.style.visibility = 'visible'; }",
                height,
            )
            return height

        def hide() -> None:
            run("() => { document.getElementById('panel').style.visibility = 'hidden'; }")

        def shot(milliseconds: int) -> None:
            frames.append((Image.open(io.BytesIO(page.screenshot())).convert("RGB"), milliseconds))

        # As tall as the panel at its tallest, with a margin below it.
        tallest = max(show(improve), show(fix))
        page.set_viewport_size({"width": WIDTH, "height": PANEL["top"] + tallest + 24})
        hide()

        text(ORIGINAL)
        shot(600)
        key("⌃⌥P")
        shot(400)
        show(fix[:2])  # checking…
        shot(250)
        show(fix[2:])
        key()
        shot(1300)
        key("Tab")
        show(improve[:2])  # improving…
        shot(250)
        show(improve[2:])
        shot(350)
        key()
        shot(900)
        key("↩ Return")
        panel.evaluate("document.getElementById('primary').style.filter = 'brightness(0.8)'")  # pressed
        shot(350)
        hide()
        key()
        text(IMPROVED, done=True)
        shot(450)
        text(IMPROVED)
        shot(900)
        browser.close()

    # Each frame with its own colours: the panel's blue and green stay as they are.
    images = [
        frame.quantize(colors=255, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE) for frame, _ in frames
    ]
    images[0].save(
        DOCS / "demo.gif",
        save_all=True,
        append_images=images[1:],
        duration=[milliseconds for _, milliseconds in frames],
        loop=0,
        optimize=True,
    )


if __name__ == "__main__":
    main()
