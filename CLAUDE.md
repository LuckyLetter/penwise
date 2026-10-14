# Penwise

Penwise fixes and improves English in any text box on a Mac: press ⌃⌥P, check the changes, press Return.
It is for people who want better English without thinking about the tool.

## The rule: simpler for the user, always

Every change must make Penwise simpler to install, set up and use, never harder. When in doubt, leave it out.

- **One shortcut, one button.** ⌃⌥P opens the panel; its one button always does the obvious next step, and
  Return presses it. Esc or a click elsewhere closes it.
- **No extra steps.** Read the text without making the user select or copy; put the fix back without making them
  paste; pick sensible defaults instead of asking.
- **No Terminal for everyday use.** Setup, settings and updates should be reachable from the app and the menu bar.
- **Plain words.** Messages say what happened and what to do, in everyday language; nothing technical.
- **Safe.** Never paste the fix next to the original text, and never change numbers, citations, code or links on
  its own: when unsure, copy the fix and say so.
- **Test with real apps.** Behaviour differs between apps (Chrome, Electron apps such as Claude, WeChat,
  terminals). The hotkey log (`~/Library/Logs/penwise-hotkey.log`, shown by `penwise doctor`) says what happened,
  without the user's text.

## Development

- Checks: `ruff check . && ruff format --check . && pytest` (the panel tests need Playwright's Chromium; the
  Hammerspoon Spoon runs under `lupa` with `tests/hs_stub.lua`; `tests/test_macos.py` runs only on a real Mac).
- Code: `src/penwise/` (Python engine and CLI) and `src/penwise/hammerspoon/Penwise.spoon/` (hotkey, reading and
  pasting text: `init.lua`; the review panel: `panel.html`).
- For every change users get with `penwise update`, raise the version in `src/penwise/__init__.py`,
  `pyproject.toml` and `obj.version` in the Spoon's `init.lua` together.
