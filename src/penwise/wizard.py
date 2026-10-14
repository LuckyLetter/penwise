"""`penwise setup`: a guided setup that writes the config and installs the hotkey.

Each question has a suggested answer, so pressing Return all the way through
gives a working setup.
"""

from __future__ import annotations

import getpass
import platform
import shutil
import subprocess
import time
import webbrowser
from typing import TypeVar

from penwise import config, engine, keychain, ollama, presets, setup_mac
from penwise.config import Config, ConfigError
from penwise.llm import ChatClient, LLMError

T = TypeVar("T")

TEST_SENTENCE = "This sentence have a error."


def run() -> int:
    print("Penwise setup. Press Return to accept the suggestion in [brackets].\n")
    provider = choose("Where should the model run?", [(p, f"{p.name}: {p.blurb}") for p in presets.PROVIDERS])
    if provider is presets.OPENROUTER:
        values = _openrouter()
    elif provider is presets.OLLAMA:
        values = _ollama()
    else:
        values = _custom()
    if values is None:
        return 1
    # Small local models often give wrong reasons, so explanations start off for them.
    values["explain"] = presets.explains_well(provider, values["base_url"])

    if not test_connection(values) and not confirm("Save these settings anyway?", default=False):
        print("Nothing was saved. Run `penwise setup` again when you're ready.")
        return 1
    _save(values)

    hotkey = platform.system() == "Darwin" and confirm("\nSet up the hotkey that works in every app?")
    if hotkey and setup_hotkey():
        print(
            "\nAll set! Click in any text box and press ⌃⌥P (Control+Option+P).\n"
            "Return puts the fix in; Esc closes. (⌃⌥⇧P also improves the flow; ⌃⌥⌘P fixes without asking.)"
        )
        if confirm("Try it now on a practice note?"):
            setup_mac.open_practice_note(config.config_path().parent)
    else:
        print(f'\nAll set! Try it: penwise check "{TEST_SENTENCE}"')
    print("Not sure how to say something? Write it in your own language, as [[your idea]], or leave [[?]]:")
    print("Penwise fills it in.")
    return 0


def test_connection(values: dict) -> bool:
    print("\nTesting the model… ", end="", flush=True)
    try:
        client = ChatClient.from_config(Config(**values))
        started = time.monotonic()
        result = engine.check(TEST_SENTENCE, client.chat)
    except (ConfigError, LLMError) as exc:
        print(f"✗\n  {exc}")
        return False
    print(f'✓ "{TEST_SENTENCE}" → "{result.edited}" ({time.monotonic() - started:.1f}s)')
    return True


def setup_hotkey() -> bool:
    """Install Hammerspoon if needed, add the Penwise Spoon, and restart Hammerspoon."""
    fresh = False
    if not setup_mac.hammerspoon_installed():
        print("\nThe hotkey uses Hammerspoon, a free, open-source app that adds hotkeys to macOS.")
        if not confirm("Download and install Hammerspoon now?"):
            print("Install it from https://www.hammerspoon.org, then run `penwise setup` again.")
            return False
        print("Downloading Hammerspoon… ", end="", flush=True)
        try:
            print(f"✓ {setup_mac.install_hammerspoon()}")
        except setup_mac.SetupError as exc:
            print(f"✗\n  {exc}")
            return False
        fresh = True

    setup_mac.install_spoon()
    status = setup_mac.write_snippet(setup_mac.hammerspoon_dir() / "init.lua")
    setup_mac.restart_hammerspoon()
    print("✓ Hotkey installed, and Hammerspoon restarted to load it.")

    if fresh or status == "added":
        print(
            "\nLast step: allow Hammerspoon to copy your selection and paste the result.\n"
            "In the settings window that opens, turn on Hammerspoon under Accessibility."
        )
        setup_mac.open_accessibility_settings()
        input("Press Return when it's on. ")
    return True


def _openrouter() -> dict:
    provider = presets.OPENROUTER
    if keychain.available() and keychain.read() and confirm("\nUse the API key already saved in your Keychain?"):
        key_settings = {"api_key_command": keychain.READ_COMMAND}
    else:
        print(f"\nPenwise needs an OpenRouter API key. You can create one at {provider.key_url}")
        if confirm("Open that page in your browser?"):
            webbrowser.open(provider.key_url)
        key = ask_secret("Paste your key (it starts with sk-or-; nothing shows while you paste): ", prefix="sk-or-")
        key_settings = _store_key(key)
    model = _choose_model(provider)
    return {
        "base_url": provider.base_url,
        "model": model.id,
        "reasoning_effort": model.reasoning_effort,
        **key_settings,
    }


def _ollama() -> dict | None:
    if not shutil.which("ollama"):
        print("\nOllama isn't installed yet.")
        if not (shutil.which("brew") and confirm("Install it with Homebrew now?")):
            print("Install it from https://ollama.com, then run `penwise setup` again.")
            return None
        if not _run(["brew", "install", "ollama"]):
            return None
    if not ollama.running():
        if shutil.which("brew"):
            _run(["brew", "services", "start", "ollama"])
        else:
            print("Starting Ollama: open the Ollama app.")
        for _ in range(15):
            if ollama.running():
                break
            time.sleep(1)
        else:
            print("Ollama isn't running. Open the Ollama app (or run `ollama serve`), then run `penwise setup` again.")
            return None

    installed = ollama.models()
    model = _choose_model(presets.OLLAMA, installed)
    if model.id not in installed:
        if not confirm(f"Download {model.id} now (about 1 GB)?"):
            print(f"Download it later with: ollama pull {model.id}")
            return None
        if not _run(["ollama", "pull", model.id]):
            return None
    return {"base_url": presets.OLLAMA.base_url, "model": model.id}


def _custom() -> dict:
    print("\nAny service with an OpenAI-compatible chat API works.")
    base_url = ask("API base URL (it usually ends in /v1):", required=True)
    model = ask("Model id:", required=True)
    key = ask_secret("API key (press Return if the service needs none): ", required=False)
    return {"base_url": base_url, "model": model, **(_store_key(key) if key else {})}


def _choose_model(provider: presets.Provider, installed: set[str] = frozenset()) -> presets.Model:
    """Pick a suggested model, one already on this computer (`installed`), or type an id."""
    suggested = {m.id for m in provider.models}
    models = [
        *provider.models,
        *(presets.Model(name, "") for name in sorted(installed - suggested) if "embed" not in name),
    ]
    options = [(m, f"{m.id:<30} {m.blurb}{' (installed)' if m.id in installed else ''}".rstrip()) for m in models]
    options.append((None, "another model (type its id)"))
    # Return picks the first model that needs no download.
    default = next((n for n, m in enumerate(models, 1) if m.id in installed), 1)
    model = choose("\nWhich model?", options, default)
    return model or presets.Model(ask("Model id:", required=True), "")


def _store_key(key: str) -> dict:
    if keychain.available():
        keychain.save(key)
        print("✓ Key saved in your macOS Keychain.")
        return {"api_key_command": keychain.READ_COMMAND}
    print("The key will be kept in the config file, readable only by you.")
    return {"api_key": key}


def _save(values: dict) -> None:
    path = config.config_path()
    note = ""
    if path.exists():
        backup = path.with_name(path.name + ".bak")
        shutil.copyfile(path, backup)
        note = f" (your previous settings are in {backup.name})"
    # Empty strings mean "use the default", so they are left out of the file.
    config.write_config({k: v for k, v in values.items() if v != ""}, path)
    print(f"✓ Settings saved to {path}{note}")


def _run(command: list[str]) -> bool:
    print(f"$ {' '.join(command)}")
    return subprocess.run(command).returncode == 0


# Prompts. Kept tiny so tests can drive the whole setup by replacing input().


def ask(prompt: str, default: str = "", required: bool = False) -> str:
    while True:
        answer = input(f"{prompt} {f'[{default}] ' if default else ''}").strip() or default
        if answer or not required:
            return answer
        print("This one is needed.")


def ask_secret(prompt: str, prefix: str = "", required: bool = True) -> str:
    while True:
        answer = getpass.getpass(prompt).strip()
        if not answer and not required:
            return ""
        if answer and answer.startswith(prefix):
            return answer
        if answer:
            print(f"That doesn't look right: it should start with {prefix}. Copy the key again and paste it.")


def confirm(prompt: str, default: bool = True) -> bool:
    answer = input(f"{prompt} [{'Y/n' if default else 'y/N'}] ").strip().lower()
    return default if not answer else answer in ("y", "yes")


def choose(title: str, options: list[tuple[T, str]], default: int = 1) -> T:
    print(title)
    for number, (_, label) in enumerate(options, 1):
        print(f"  {number}) {label}")
    while True:
        answer = input(f"Choose [{default}]: ").strip() or str(default)
        if answer.isdigit() and 1 <= int(answer) <= len(options):
            return options[int(answer) - 1][0]
        print(f"Please type a number from 1 to {len(options)}.")
