#!/bin/bash
# Penwise inside Penwise.app: the app's own Python runs it, with the Penwise the app came with,
# or a newer one that an update installed in Penwise's folder (the app itself never changes).

RES="$(cd "$(dirname "$0")/.." && pwd)" # Penwise.app/Contents/Resources
APP="$(cd "$RES/../.." && pwd)"
SITE="$HOME/Library/Application Support/Penwise/site"
LIB="$RES/lib"
PYTHON="$RES/python/bin/python3-$(uname -m)" # arm64 or x86_64: one for each kind of Mac
if [ ! -x "$PYTHON" ]; then # a Penwise made for the other kind of Mac
  echo "This Penwise is for another kind of Mac. Download the one for yours: https://github.com/LuckyLetter/penwise/releases/latest" >&2
  exit 1
fi

version_of() { # the Penwise version in a folder of Python packages
  sed -n 's/^__version__ = "\(.*\)"$/\1/p' "$1/penwise/__init__.py" 2>/dev/null
}

newer() { # whether version $1 is newer than version $2
  awk -v a="$1" -v b="$2" 'BEGIN {
    split(a, x, "."); split(b, y, ".")
    for (i = 1; i <= 3; i++) { if (x[i] + 0 > y[i] + 0) exit 0; if (x[i] + 0 < y[i] + 0) exit 1 }
    exit 1
  }'
}

updated="$(version_of "$SITE")"
if [ -n "$updated" ] && newer "$updated" "$(version_of "$LIB")"; then
  export PYTHONPATH="$SITE:$LIB"
else
  export PYTHONPATH="$LIB"
fi
unset PYTHONHOME
# The app never writes in itself: that would break its signature. Its code comes compiled.
export PYTHONDONTWRITEBYTECODE=1
export PENWISE_APP="$APP" PENWISE_COMMAND="$RES/bin/penwise"
exec "$PYTHON" -s -m penwise "$@"
