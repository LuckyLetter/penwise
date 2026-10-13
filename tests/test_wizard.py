"""Drive `penwise setup` end to end, with typed answers and the fake model server."""

import dataclasses
import os
import stat

import pytest

from penwise import cli, config, keychain, presets, setup_mac, wizard


@pytest.fixture
def answers(monkeypatch):
    """Queue answers for input() and getpass(); the test fails if setup asks for more."""
    typed: list[str] = []
    secrets: list[str] = []
    monkeypatch.setattr("builtins.input", lambda prompt="": typed.pop(0))
    monkeypatch.setattr(wizard.getpass, "getpass", lambda prompt="": secrets.pop(0))
    return typed, secrets


class FakeKeychain:
    """Stands in for the macOS Keychain, including the `security` command the config calls."""

    def __init__(self, tmp_path, monkeypatch):
        self.file = tmp_path / "keychain"
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        security = bin_dir / "security"
        security.write_text(f"#!/bin/sh\ncat '{self.file}' 2>/dev/null\n")
        security.chmod(0o755)
        monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
        monkeypatch.setattr(keychain, "available", lambda: True)
        monkeypatch.setattr(keychain, "save", self.save)
        monkeypatch.setattr(keychain, "read", self.read)

    def save(self, key):
        self.file.write_text(key)

    def read(self):
        return self.file.read_text() if self.file.exists() else ""


@pytest.fixture
def mac(monkeypatch, tmp_path):
    """Pretend to be a Mac with Hammerspoon installed; record what setup does to it."""
    done = []
    monkeypatch.setattr(wizard.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(setup_mac, "hammerspoon_installed", lambda: True)
    monkeypatch.setattr(setup_mac, "hammerspoon_dir", lambda: tmp_path / "hammerspoon")
    monkeypatch.setattr(setup_mac, "restart_hammerspoon", lambda: done.append("restart"))
    monkeypatch.setattr(setup_mac, "open_accessibility_settings", lambda: done.append("accessibility"))
    monkeypatch.setattr(wizard.webbrowser, "open", lambda url: done.append(f"open {url}"))
    return done, FakeKeychain(tmp_path, monkeypatch)


@pytest.fixture
def openrouter(server, monkeypatch):
    """Point the OpenRouter choice at the fake server."""
    provider = dataclasses.replace(presets.OPENROUTER, base_url=server.url)
    monkeypatch.setattr(presets, "OPENROUTER", provider)
    monkeypatch.setattr(presets, "PROVIDERS", (provider, presets.OLLAMA, presets.CUSTOM))
    return provider


def test_pressing_return_everywhere_gives_a_working_setup(isolated, answers, mac, openrouter, capsys):
    typed, secrets = answers
    done, store = mac
    typed += ["", "", "", "", "", ""]  # provider, open browser, model, hotkey, accessibility "Return when on"
    secrets.append("sk-or-v1-abc123")

    assert wizard.run() == 0

    cfg = config.load()
    assert (cfg.base_url, cfg.model) == (openrouter.base_url, "mistralai/mistral-small-2603")
    assert cfg.api_key_command == keychain.READ_COMMAND and store.read() == "sk-or-v1-abc123"
    assert cfg.explain is True and cfg.reasoning_effort == ""
    assert done == [f"open {openrouter.key_url}", "restart", "accessibility"]
    assert "spoon.Penwise:bindHotkeys" in (setup_mac.hammerspoon_dir() / "init.lua").read_text()
    out = capsys.readouterr().out
    assert '→ "This sentence has an error."' in out
    assert "All set!" in out


def test_choosing_a_thinking_model_turns_thinking_down(isolated, answers, mac, openrouter):
    typed, secrets = answers
    typed += ["1", "n", "2", "n"]  # OpenRouter, don't open browser, GPT-6 Luna, no hotkey
    secrets.append("sk-or-v1-abc123")
    assert wizard.run() == 0
    cfg = config.load()
    assert (cfg.model, cfg.reasoning_effort) == ("openai/gpt-6-luna", "none")


def test_a_key_already_in_the_keychain_is_reused(isolated, answers, mac, openrouter):
    typed, secrets = answers
    mac[1].save("sk-or-v1-saved")
    typed += ["", "", "", "n"]  # OpenRouter, reuse key, model, no hotkey
    assert wizard.run() == 0
    assert config.load().api_key_command == keychain.READ_COMMAND
    assert secrets == []


def test_a_mistyped_key_is_asked_again(isolated, answers, mac, openrouter, capsys):
    typed, secrets = answers
    typed += ["", "n", "", "n"]
    secrets += ["my-password", "sk-or-v1-abc123"]
    assert wizard.run() == 0
    assert "should start with sk-or-" in capsys.readouterr().out


def test_ollama_with_the_model_already_downloaded(isolated, answers, server, monkeypatch):
    typed, _ = answers
    ollama = dataclasses.replace(presets.OLLAMA, base_url=server.url)
    monkeypatch.setattr(presets, "OLLAMA", ollama)
    monkeypatch.setattr(presets, "PROVIDERS", (presets.OPENROUTER, ollama, presets.CUSTOM))
    monkeypatch.setattr(wizard.platform, "system", lambda: "Linux")
    monkeypatch.setattr(wizard.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(wizard, "_ollama_running", lambda: True)
    monkeypatch.setattr(wizard, "_ollama_models", lambda: {"gemma3:1b"})
    typed += ["2", ""]  # Ollama, first model
    assert wizard.run() == 0
    cfg = config.load()
    assert (cfg.base_url, cfg.model, cfg.explain) == (server.url, "gemma3:1b", False)


def test_ollama_offers_the_models_you_already_have(isolated, answers, server, monkeypatch, capsys):
    typed, _ = answers
    ollama = dataclasses.replace(presets.OLLAMA, base_url=server.url)
    monkeypatch.setattr(presets, "OLLAMA", ollama)
    monkeypatch.setattr(presets, "PROVIDERS", (presets.OPENROUTER, ollama, presets.CUSTOM))
    monkeypatch.setattr(wizard.platform, "system", lambda: "Linux")
    monkeypatch.setattr(wizard.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(wizard, "_ollama_running", lambda: True)
    monkeypatch.setattr(wizard, "_ollama_models", lambda: {"llama3.2:1b", "qwen3:4b", "nomic-embed-text:latest"})
    typed += ["2", ""]  # Ollama, and Return: the first installed model, no download needed
    assert wizard.run() == 0
    assert config.load().model == "llama3.2:1b"
    out = capsys.readouterr().out
    assert "qwen3:4b" in out and "(installed)" in out
    assert "nomic-embed-text" not in out  # not a chat model


def test_another_service_without_a_keychain_keeps_the_key_private(isolated, answers, server, monkeypatch):
    typed, secrets = answers
    monkeypatch.setattr(wizard.platform, "system", lambda: "Linux")
    monkeypatch.setattr(keychain, "available", lambda: False)
    typed += ["3", server.url, "some-model"]
    secrets.append("secret-key")
    assert wizard.run() == 0
    cfg = config.load()
    assert (cfg.base_url, cfg.model, cfg.api_key) == (server.url, "some-model", "secret-key")
    assert cfg.explain is False  # a server on this computer: likely a small model
    assert stat.S_IMODE(config.config_path().stat().st_mode) == 0o600


def test_a_failed_test_saves_nothing_unless_asked(isolated, answers, monkeypatch, capsys):
    typed, secrets = answers
    monkeypatch.setattr(keychain, "available", lambda: False)
    typed += ["3", "http://127.0.0.1:9/v1", "some-model", ""]  # ..., "Save anyway?" → default No
    secrets.append("")
    assert wizard.run() == 1
    assert not config.config_path().exists()
    assert "Could not reach" in capsys.readouterr().out


def test_previous_settings_are_backed_up(isolated, answers, server, monkeypatch):
    typed, secrets = answers
    monkeypatch.setattr(wizard.platform, "system", lambda: "Linux")
    monkeypatch.setattr(keychain, "available", lambda: False)
    config.write_template()
    typed += ["3", server.url, "some-model"]
    secrets.append("")
    assert wizard.run() == 0
    backup = config.config_path().with_name("config.toml.bak")
    assert backup.read_text() == config.TEMPLATE


def test_setup_outside_a_terminal_explains_itself(isolated, monkeypatch, capsys):
    def no_input(prompt=""):
        raise EOFError

    monkeypatch.setattr("builtins.input", no_input)
    assert cli.main(["setup"]) == 1
    assert "run it in a terminal" in capsys.readouterr().err
