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
- Languages: what users see is written in English in the code and goes through `tr()` (Python, the Spoon and the
  panel alike; `N_()` marks a text translated where it is shown later). Each language is one file,
  `Penwise.spoon/locales/<code>.json` (`name`, `tag`, `model_name`, `strings` by the English text), found by itself:
  adding a language is adding its file. `tests/test_i18n.py` fails until every language has every text, so a change
  to a text comes with its translations. The practice note stays English: Penwise checks it. The README's
  translations are `docs/readme/<code>.md`, each named in the line of languages at the top of `README.md` (never
  more files in the root).
- For every change users get with `penwise update`, raise the version in `src/penwise/__init__.py`,
  `pyproject.toml` and `obj.version` in the Spoon's `init.lua` together.
- Before committing, check pytest's own exit status: piped into `tail`, a failing run looks like a passing one.
- The app: *Penwise.app* (built with `installer/build_app.py`) has its own Python, Penwise and Hammerspoon inside;
  `installer/app/launcher.sh` sets it up when it opens and `installer/app/penwise.sh` runs Penwise. It never writes
  in itself (that breaks its signature): updates and its Hammerspoon go in `~/Library/Application Support/Penwise`.
  It comes as `Penwise.dmg` (LZMA): `hdiutil` on a Mac; on Linux `mkfs.hfsplus` and libdmg-hfsplus's `hfsplus` and
  `dmg` (`PENWISE_DMG_TOOLS`; the Release workflow builds them). Its icons are drawn by `installer/app/make_icon.py`
  (`Penwise.icns`, and the Spoon's `menubar.png`), the disk image's window by `make_dmg_window.py`, and the
  README's animation and pictures of the panel by `docs/make_demo.py` and `docs/make_screenshots.py`.
  The Release workflow publishes it, with the wheel Penwise.app updates itself from; the release page is
  `.github/release-notes.md`, updated for each release.

## On a real Mac

- No Apple Events to other apps (`osascript -e 'tell application …'`, `quit app …`): macOS asks the user for
  permission to control that app. Quit Hammerspoon with a signal, trash with NSFileManager (`uninstall.trash`).
- `~/.Trash` and other private folders are closed to programs without Full Disk Access; go through the APIs made for
  them.
- macOS 26 may ask before Hammerspoon reads what another app copied (Privacy & Security → Paste from Other Apps):
  read the clipboard only when the user means to copy or paste, never just because a window opened.
- Started from Hammerspoon, `penwise` has its PATH, without `~/.local/bin`: find uv and the `penwise` command
  explicitly, and put uv's tool folder first before anything writes `init.lua`.
- Hammerspoon started by Penwise (its app, its installer, a Terminal) counts as Penwise's for macOS's permissions,
  which then wants Accessibility for both: start it through launchd (`setup_mac.restart_hammerspoon`), as at login.
  launchd runs `open` on it: started from its program file, Hammerspoon runs, but macOS 26 and later show nothing of
  it (no window, no menu bar icon). Penwise.app waits until Penwise, in Hammerspoon, takes its `opened` note, and says
  so when it doesn't: it never quits without a window or a word.
- People who use Hammerspoon themselves keep their own choices: icons, login item and `init.lua` change only when
  the installer put Hammerspoon there for Penwise (`Penwise.background`).
