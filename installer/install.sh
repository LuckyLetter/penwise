#!/bin/bash
# Install Penwise on a Mac with nothing to type: uv (which installs Python apps), Penwise, and
# the shortcut (Penwise downloads Hammerspoon for it if needed). Penwise then opens its window
# to choose a model.
#
# "Install Penwise.app" runs this script with the Penwise it carries and shows dialogs; the
# details go to ~/Library/Logs/penwise-install.log. From the Terminal:
#
#   bash install.sh [what to install: a penwise .whl, or git+https://… (the default)]

set -u

SOURCE="${1:-}"
LOG="$HOME/Library/Logs/penwise-install.log"
TITLE="Install Penwise"

# Run as "Install Penwise.app"? Then the Penwise to install is inside it.
APP=""
case "$0" in
  *.app/Contents/MacOS/*) APP="${0%/Contents/MacOS/*}" ;;
esac
if [ -z "$SOURCE" ] && [ -n "$APP" ]; then
  for wheel in "$APP"/Contents/Resources/penwise-*.whl; do
    if [ -e "$wheel" ]; then SOURCE="$wheel"; fi
  done
fi
SOURCE="${SOURCE:-git+https://github.com/LuckyLetter/penwise}"

# A dialog; the last button is the default. Prints the button clicked (nothing for Cancel).
ask() {
  osascript - "$TITLE" "$@" 2>/dev/null <<'END'
on run argv
  set dialogTitle to item 1 of argv
  set dialogText to item 2 of argv
  set choices to items 3 thru -1 of argv
  activate
  return button returned of (display dialog dialogText with title dialogTitle buttons choices default button (count of choices) with icon note)
end run
END
}

# A dialog that stays up while Penwise installs.
show_progress() {
  if [ -z "$APP" ]; then return 0; fi
  osascript - "$TITLE" "$1" >/dev/null 2>&1 <<'END' &
on run argv
  activate
  display dialog (item 2 of argv) with title (item 1 of argv) buttons {"Hide"} default button 1 with icon note giving up after 900
end run
END
  PROGRESS=$!
}

hide_progress() {
  if [ -n "${PROGRESS:-}" ]; then
    kill "$PROGRESS" 2>/dev/null
    PROGRESS=""
  fi
}

step() {
  printf '\n==> %s\n' "$1"
}

fail() {
  hide_progress
  printf '\n✗ %s\n' "$1"
  if [ -n "$APP" ] && [ "$(ask "Penwise couldn't be installed. $1" "Show Details" "OK")" = "Show Details" ]; then
    open -e "$LOG"
  fi
  exit 1
}

find_uv() {
  for uv in "$(command -v uv)" "$HOME/.local/bin/uv" /opt/homebrew/bin/uv /usr/local/bin/uv; do
    if [ -n "$uv" ] && [ -x "$uv" ]; then
      echo "$uv"
      return 0
    fi
  done
  return 1
}

if [ "$(uname)" != Darwin ]; then
  echo "This installer is for macOS. Elsewhere: uv tool install git+https://github.com/LuckyLetter/penwise"
  exit 1
fi
if [ -n "$APP" ]; then
  mkdir -p "$(dirname "$LOG")"
  exec >>"$LOG" 2>&1
fi
echo "== $(date): installing Penwise from $SOURCE"

if [ -n "$APP" ]; then
  also=" and Hammerspoon, the free app that gives Penwise its shortcut"
  if [ -d /Applications/Hammerspoon.app ] || [ -d "$HOME/Applications/Hammerspoon.app" ]; then also=""; fi
  answer="$(ask "Penwise checks your English in any app: press ⌃⌥P in a text box.

This installs Penwise$also. It takes a minute or two." "Cancel" "Install")"
  if [ "$answer" != "Install" ]; then exit 0; fi
fi
show_progress "Installing Penwise…

This takes a minute or two. Penwise opens when it's ready."

step "uv, which installs Python apps"
UV="$(find_uv)" || { curl -LsSf https://astral.sh/uv/install.sh | sh && UV="$(find_uv)"; } ||
  fail "Couldn't download uv. Check your internet connection, then try again."
echo "$UV"

step "Penwise"
# A Python of uv's own: the one macOS comes with may ask to install developer tools first.
managed="--managed-python"
if ! "$UV" tool install --help 2>/dev/null | grep -q -- "--managed-python"; then
  managed="--python-preference=only-managed" # older uv
fi
"$UV" tool install --force --reinstall "$managed" --python 3.13 "$SOURCE" ||
  fail "Couldn't install Penwise. Check your internet connection, then try again."
BIN="$("$UV" tool dir --bin)"
PENWISE="$BIN/penwise"

step "The shortcut"
if ! output="$(PATH="$BIN:$PATH" "$PENWISE" setup-mac --background 2>&1)"; then
  printf '%s\n' "$output"
  fail "$(printf '%s\n' "$output" | tail -n 1)"
fi
printf '%s\n' "$output"
for _ in 1 2 3 4 5 6 7 8 9 10; do
  if pgrep -x Hammerspoon >/dev/null; then break; fi
  sleep 1
done
pgrep -x Hammerspoon >/dev/null || fail "Hammerspoon didn't start. Open it from your Applications folder."

hide_progress
version="$("$PENWISE" --version)" # penwise 1.2.3
version="Penwise ${version#penwise }"
printf '\n✓ %s\n' "$version"
if "$PENWISE" settings | grep -q '"configured": true'; then
  message="$version is ready. Press ⌃⌥P in any text box to check your English."
  if [ -n "$APP" ]; then ask "$message" "OK" >/dev/null; else echo "$message"; fi
elif [ -z "$APP" ]; then
  echo "Choose a model in the Penwise window, then press ⌃⌥P in any text box."
fi
