"""Penwise's languages: each one is a file in the Spoon's `locales` folder, and has every text the
app shows (with the same {names} to fill in), and nothing else.

To start a new language, copy a file there to `<code>.json`, set its `name` (in itself), `tag`
and `model_name`, and translate its `strings`; these tests say what is missing or left over.
`python tests/test_i18n.py` prints every text to translate.
"""

import ast
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from penwise import i18n, lessons  # noqa: E402

SOURCE = ROOT / "src" / "penwise"
SPOON = SOURCE / "hammerspoon" / "Penwise.spoon"
LAUNCHER = ROOT / "installer" / "app" / "launcher.sh"
PLACEHOLDER = re.compile(r"\{(\w+)\}")


def python_texts() -> set[str]:
    """tr("…") and N_("…") in Penwise's Python."""
    found = set()
    for path in SOURCE.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) in ("tr", "N_") and node.args:
                first = node.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    found.add(first.value)
    return found


def lesson_texts() -> set[str]:
    """The fixed titles and notes for each change (lessons.py), translated as they are shown."""
    notes = {value for name, value in vars(lessons).items() if name.endswith("_NOTE") and isinstance(value, str)}
    return (
        notes
        | {lessons.POSSESSIVE}
        | set(lessons.LABELS.values())
        | set(lessons.NOTES.values())
        | set(lessons.CONFUSABLE.values())
        | set(lessons.RULE_TITLES.values())
    )


def _literals(pattern: str, text: str) -> set[str]:
    return {json.loads(f'"{match}"') for match in re.findall(pattern, text)}


def lua_texts() -> set[str]:
    return _literals(r'\b(?:tr|N_)\(\s*"((?:[^"\\]|\\.)*)"', (SPOON / "init.lua").read_text(encoding="utf-8"))


def panel_texts() -> set[str]:
    page = (SPOON / "panel.html").read_text(encoding="utf-8")
    return _literals(r'\b(?:tr|N_)\(\s*"((?:[^"\\]|\\.)*)"', page) | set(
        re.findall(r'data-tr(?:-title|-label)?="([^"]*)"', page)
    )


def launcher_texts() -> set[str]:
    """Penwise.app's dialogs: their texts and buttons (not what comes in a variable)."""
    found = set()
    for line in LAUNCHER.read_text(encoding="utf-8").splitlines():
        line = re.sub(r'"\$\([^)]*\)"', "", line)  # "$(…)": what a command printed
        call = re.search(r'\b(?:dialog|fail) (".*)$', line)
        if call:
            found |= {text for text in re.findall(r'"([^"]*)"', call[1]) if text and "$" not in text}
    return found


def all_texts() -> set[str]:
    return python_texts() | lesson_texts() | lua_texts() | panel_texts() | launcher_texts()


LANGUAGES = sorted(path.stem for path in i18n.LOCALES.glob("*.json"))


def test_texts_are_found_everywhere():
    assert "Settings" in panel_texts() | lua_texts()  # the window, the menu
    assert "Paste your model name." in python_texts()
    assert "Subject–verb agreement" in lesson_texts()
    assert {"OK", "Cancel", "Move to Applications", "Penwise didn't start. Open it again."} <= launcher_texts()
    assert not any(PLACEHOLDER.search(text) and "${" in text for text in all_texts())


def test_penwise_speaks_chinese_japanese_and_korean():
    assert {"zh", "ja", "ko"} <= set(LANGUAGES)
    assert i18n.languages() == {"en": "English", "ja": "日本語", "ko": "한국어", "zh": "中文"} | {
        code: i18n.locale(code)["name"] for code in LANGUAGES
    }


@pytest.mark.parametrize("language", LANGUAGES)
def test_each_language_has_every_text_and_nothing_else(language):
    data = json.loads((i18n.LOCALES / f"{language}.json").read_text(encoding="utf-8"))
    assert data["name"] and data["tag"] and data["model_name"]
    strings = data["strings"]
    texts = all_texts()
    assert not sorted(texts - set(strings)), "not translated yet"
    assert not sorted(set(strings) - texts), "no longer used: remove them"
    for english, translated in strings.items():
        assert translated.strip(), english
        assert set(PLACEHOLDER.findall(translated)) == set(PLACEHOLDER.findall(english)), english


README_TRANSLATIONS = sorted((ROOT / "docs" / "readme").glob("*.md"))


def test_the_readme_s_translations_are_one_folder_and_linked_both_ways():
    assert README_TRANSLATIONS and sorted(ROOT.glob("README*.md")) == [ROOT / "README.md"]
    languages = (ROOT / "README.md").read_text(encoding="utf-8").splitlines()[2]  # the line under the title
    for path in README_TRANSLATIONS:
        assert f"](docs/readme/{path.name})" in languages, f"{path.name} is not in README.md's languages"
        text = path.read_text(encoding="utf-8")
        assert "](../../README.md)" in text.splitlines()[2]  # and back to English, and the other languages
        # Its links and pictures, relative to the folder it is in, are there.
        for target in re.findall(r'\]\((?!https?:)([^)#]+)|src(?:set)?="([^"]+)"', text):
            target = next(part for part in target if part)
            assert (path.parent / target).resolve().exists(), f"{path.name}: {target}"


def test_tr_fills_in_the_translation(monkeypatch):
    monkeypatch.setattr(i18n, "_language", "zh")
    english = "Downloading {model}… {percent}% of {size}"
    shown = i18n.tr(english, model="gemma3:1b", percent=40, size="815 MB")
    assert (
        "gemma3:1b" in shown
        and "40" in shown
        and "815 MB" in shown
        and shown != english.format(model="gemma3:1b", percent=40, size="815 MB")
    )
    assert i18n.tr("A text Penwise doesn't have") == "A text Penwise doesn't have"  # English, then
    i18n.use("xx")
    assert i18n.language() == "en"


def test_a_check_shows_its_notes_in_the_language_and_keeps_them_in_english(monkeypatch):
    from penwise import engine

    monkeypatch.setattr(i18n, "_language", "zh")
    result = engine.check("She have two dataset.", lambda system, messages: "She has two datasets.")
    shown = result.to_dict()["changes"][0]
    assert shown["label"] == i18n.strings("zh")["Subject–verb agreement"]
    assert shown["note"] == i18n.strings("zh")[lessons.AGREEMENT_NOTE]
    assert result.changes[0].label == "Subject–verb agreement"  # as the history keeps it


def test_the_model_gives_its_reasons_in_the_language():
    from penwise import prompts

    system, messages = prompts.explain_messages("a", "b", [("a", "b")], language="ja")
    assert "Japanese" in system and "Japanese" in messages[-1]["content"]
    system, messages = prompts.explain_messages("a", "b", [("a", "b")])
    assert "Write the reasons in" not in system + messages[-1]["content"]


if __name__ == "__main__":
    print(json.dumps(sorted(all_texts()), ensure_ascii=False, indent=1))
