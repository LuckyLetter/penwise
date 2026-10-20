"""The language of Penwise's windows, menus and notes.

Every text is written in English and looked up, by that English text, in the language chosen
in the settings (`language` in the config). Each language is one file in the Spoon's `locales`
folder, where the Hammerspoon side, the panel and Penwise.app read it too:

    locales/zh.json   {"name": "中文", "tag": "zh-Hans", "model_name": "Simplified Chinese",
                       "strings": {"Settings": "设置", ...}}

`name` is the language in itself, as the settings list it; `tag` its BCP 47 tag, for the window;
`model_name` how the model is asked to write in it. To add a language, add its file: nothing
else changes. A text not translated yet shows in English.
"""

from __future__ import annotations

import json
import re
from functools import cache
from pathlib import Path

LOCALES = Path(__file__).parent / "hammerspoon" / "Penwise.spoon" / "locales"
_PLACEHOLDER = re.compile(r"\{(\w+)\}")

_language = "en"


@cache
def locale(language: str) -> dict:
    """The file for `language`, or {} (English, or none such)."""
    if language == "en" or not re.fullmatch(r"[A-Za-z]{2,3}(-[A-Za-z0-9]+)*", language):
        return {}
    try:
        data = json.loads((LOCALES / f"{language}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def languages() -> dict[str, str]:
    """Each language Penwise has, by its code, with its name in itself: how you find yours."""
    found = {"en": "English"}
    for path in sorted(LOCALES.glob("*.json")):
        if name := locale(path.stem).get("name"):
            found[path.stem] = name
    return found


def use(language: str) -> None:
    """Show Penwise's words in `language` from now on (English when Penwise doesn't have it)."""
    global _language
    _language = language if language in languages() else "en"


def language() -> str:
    return _language


def model_name(language: str) -> str:
    """How to name `language` when asking the model to write in it ("" for English)."""
    return locale(language).get("model_name", "")


def strings(language: str) -> dict[str, str]:
    """The translations into `language`, by their English text."""
    found = locale(language).get("strings")
    return found if isinstance(found, dict) else {}


def N_(text: str) -> str:
    """Marks `text` for translation where it is shown, later, with tr(): it stays English till then."""
    return text


def tr(text: str, **values: object) -> str:
    """`text` in the chosen language, with each {name} filled in from `values`."""
    translated = strings(_language).get(text) or text
    if not values:
        return translated
    return _PLACEHOLDER.sub(lambda m: str(values[m[1]]) if m[1] in values else m[0], translated)
