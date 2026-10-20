#!/bin/bash
# Penwise.app. The first time it opens, it sets Penwise up, with nothing to download: its copy of
# Hammerspoon (the free app that gives Penwise its shortcut, kept in Penwise's folder) and the
# shortcut; the Penwise window then opens to choose a model. After that, opening the app opens
# Penwise's settings. Meanwhile its icon bounces in the Dock, as any app's does while it opens; a
# dialog says only what went wrong. What happened goes to ~/Library/Logs/penwise-install.log.

set -u
APP="$(cd "$(dirname "$0")/../.." && pwd)"
RES="$APP/Contents/Resources"
PENWISE="$RES/bin/penwise"
SUPPORT="$HOME/Library/Application Support/Penwise"
LOG="$HOME/Library/Logs/penwise-install.log"
VERSION="$(cat "$RES/version" 2>/dev/null)"
LSREGISTER=/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister
# Penwise's languages, one file each, as its window uses them; and the one chosen in its settings.
LOCALES="$RES/lib/penwise/hammerspoon/Penwise.spoon/locales"
CONFIG="${PENWISE_CONFIG:-${XDG_CONFIG_HOME:-$HOME/.config}/penwise/config.toml}"
LANGUAGE="$(sed -n 's/^language *= *"\([A-Za-z0-9-]*\)".*/\1/p' "$CONFIG" 2>/dev/null | tail -n 1)"

# A dialog in the language chosen in Penwise's settings (English until then): its text, a detail
# after it as it is, and its buttons, the last one pressed by Return. Whether that one was clicked.
dialog() {
  local problem
  problem="$(osascript -l JavaScript - "$LOCALES/${LANGUAGE:-en}.json" "$@" 2>&1 >/dev/null <<'END'
function run([file, text, detail, ...buttons]) {
  let strings = {};
  try {
    strings = JSON.parse($.NSString.stringWithContentsOfFileEncodingError(file, $.NSUTF8StringEncoding, null).js).strings;
  } catch (error) {} // English
  const tr = (english) => (strings && strings[english]) || english;
  const app = Application.currentApplication();
  app.includeStandardAdditions = true;
  app.activate();
  const labels = buttons.map(tr);
  const options = { withTitle: "Penwise", buttons: labels, defaultButton: labels.length, withIcon: "note" };
  if (labels.length > 1) options.cancelButton = 1;
  app.displayDialog(tr(text) + (detail ? " " + detail : ""), options);
}
END
)" && return 0
  case "$problem" in *-128*) return 1 ;; esac # Cancel
  # Its script didn't run: the same dialog, in English.
  osascript - "$@" >/dev/null 2>&1 <<'END'
on run argv
  set message to item 1 of argv
  if item 2 of argv is not "" then set message to message & " " & item 2 of argv
  set choices to items 3 thru -1 of argv
  activate
  if (count of choices) > 1 then
    display dialog message with title "Penwise" buttons choices default button (count of choices) cancel button 1 with icon note
  else
    display dialog message with title "Penwise" buttons choices default button 1 with icon note
  end if
end run
END
}

fail() { # fail TEXT [DETAIL]: say so, and stop
  echo "✗ $1${2:+ $2}"
  dialog "$1" "${2:-}" "OK"
  exit 1
}

answered() { # whether Penwise, in Hammerspoon, took the note (opening its window) within $1 half-seconds
  local waited=0
  while [ -e "$SUPPORT/opened" ]; do
    [ "$waited" -ge "$1" ] && return 1
    waited=$((waited + 1))
    sleep 0.5
  done
}

offer_to_move() { # whether "Move to Applications" was clicked
  dialog "Penwise works from your Applications folder. Move it there and open it?" "" "Cancel" "Move to Applications"
}

mkdir -p "$(dirname "$LOG")" "$SUPPORT"
exec >>"$LOG" 2>&1
echo "== $(date): opening Penwise $VERSION at $APP"

# Opened from the disk image, or where it was downloaded (macOS then runs a hidden copy of it): as
# Mac apps do, it offers to move itself to Applications, in place of an older Penwise there, and
# opens from there. Without administrator rights, that's the Applications folder in your home.
case "$APP" in
  /Volumes/* | */AppTranslocation/*)
    if offer_to_move; then
      PLACE=/Applications
      [ -w "$PLACE" ] || PLACE="$HOME/Applications"
      echo "moving to $PLACE"
      # Copied first, then in place of the old one: the hidden copy may be a view of that very app.
      rm -rf "$PLACE/Penwise.app.new"
      { mkdir -p "$PLACE" && ditto "$APP" "$PLACE/Penwise.app.new" && rm -rf "$PLACE/Penwise.app" &&
        mv "$PLACE/Penwise.app.new" "$PLACE/Penwise.app"; } || {
        rm -rf "$PLACE/Penwise.app.new"
        fail "Penwise couldn't move itself. Drag it into your Applications folder, then open it from there."
      }
      xattr -dr com.apple.quarantine "$PLACE/Penwise.app" 2>/dev/null # you opened it: yours to run
      open "$PLACE/Penwise.app"
    fi
    exit 0
    ;;
esac

# Set up already, and the same version: open the settings. Penwise takes this note as it does;
# when it doesn't, it is set up again.
if [ "$(cat "$SUPPORT/app-version" 2>/dev/null)" = "$VERSION $APP" ] && pgrep -x Hammerspoon >/dev/null &&
  grep -q "spoon.Penwise" "$HOME/.hammerspoon/init.lua" 2>/dev/null; then
  touch "$SUPPORT/opened"
  open -g "hammerspoon://penwiseSettings"
  answered 6 && exit 0
  echo "Penwise didn't answer: setting it up again"
fi

# Its files came from the internet: macOS marks each one and would stop the app's own Python. You
# opened Penwise, so they are yours to run.
xattr -dr com.apple.quarantine "$APP" 2>/dev/null
# Its icon in Applications and the Dock: macOS may still show a blank one it kept for an earlier
# Penwise here, until it reads the app again.
touch "$APP" 2>/dev/null
"$LSREGISTER" -f "$APP" 2>/dev/null

# Someone who has Hammerspoon already keeps theirs; otherwise Penwise's copy goes in Penwise's
# folder, and again when Penwise comes with a newer one.
if [ ! -d /Applications/Hammerspoon.app ] && [ ! -d "$HOME/Applications/Hammerspoon.app" ]; then
  bundled="$(cat "$RES/hammerspoon-version" 2>/dev/null)"
  if [ ! -d "$SUPPORT/Hammerspoon.app" ] || [ "$(cat "$SUPPORT/hammerspoon-version" 2>/dev/null)" != "$bundled" ]; then
    pkill -x Hammerspoon
    rm -rf "$SUPPORT/Hammerspoon.app"
    ditto -x -k "$RES/Hammerspoon.zip" "$SUPPORT" || fail "Penwise couldn't set itself up: its copy of Hammerspoon is damaged. Download Penwise again."
    echo "$bundled" >"$SUPPORT/hammerspoon-version"
  fi
fi

# The shortcut, with Hammerspoon out of sight when it is there just for Penwise. Hammerspoon then
# (re)starts and, told so by this note, opens Penwise's window: to choose a model the first time.
touch "$SUPPORT/opened"
if ! output="$("$PENWISE" setup-mac --background 2>&1)"; then
  printf '%s\n' "$output"
  fail "Penwise couldn't set up its shortcut." "$(printf '%s\n' "$output" | tail -n 1)"
fi
printf '%s\n' "$output"
for _ in 1 2 3 4 5 6 7 8 9 10; do
  if pgrep -x Hammerspoon >/dev/null; then break; fi
  sleep 1
done
pgrep -x Hammerspoon >/dev/null || fail "Hammerspoon didn't start. Open Penwise again."
echo "$VERSION $APP" >"$SUPPORT/app-version"
answered 30 || fail "Penwise didn't start. Open it again."
echo "✓ Penwise $VERSION"
