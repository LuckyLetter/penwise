"""Ready-made choices for `penwise setup` and `penwise model`.

The model list is a starting point picked for English correction: fast,
low cost, and good with language. Any other model id works too.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Model:
    id: str
    blurb: str
    # How long the model "thinks" before answering. Models that think by default
    # are much slower for a hotkey tool, so it is turned down where possible.
    reasoning_effort: str = ""


@dataclass(frozen=True)
class Provider:
    key: str
    name: str
    blurb: str
    base_url: str
    key_url: str = ""
    models: tuple[Model, ...] = ()
    explain: bool = True

    @property
    def needs_key(self) -> bool:
        return bool(self.key_url)


OPENROUTER = Provider(
    key="openrouter",
    name="OpenRouter",
    blurb="cloud models with one API key (easiest to start)",
    base_url="https://openrouter.ai/api/v1",
    key_url="https://openrouter.ai/settings/keys",
    models=(
        Model("mistralai/mistral-small-2603", "fast, low cost, good with language (recommended)"),
        Model("openai/gpt-6-luna", "stronger, low cost; thinking turned off for speed", "none"),
        Model("anthropic/claude-haiku-5.5", "stronger, low cost; thinking turned down for speed", "low"),
        Model("google/gemma-4-31b-it", "cheapest, a little slower"),
    ),
)

OLLAMA = Provider(
    key="ollama",
    name="Ollama",
    blurb="free and private: the model runs on this computer",
    base_url="http://localhost:11434/v1",
    models=(
        Model("gemma3:1b", "small and quick, fine on 8 GB Macs (recommended)"),
        Model("llama3.2:1b", "small and quick, an alternative to Gemma"),
    ),
    # Small local models often give wrong reasons, so explanations start off.
    explain=False,
)

CUSTOM = Provider(
    key="custom",
    name="Another service",
    blurb="any OpenAI-compatible API (OpenAI, Groq, LM Studio, ...)",
    base_url="",
)

PROVIDERS = (OPENROUTER, OLLAMA, CUSTOM)


def reasoning_effort_for(model_id: str) -> str:
    """The "thinking" setting Penwise recommends for a model ("" means the model's default)."""
    for provider in PROVIDERS:
        for model in provider.models:
            if model.id == model_id:
                return model.reasoning_effort
    return ""


def provider_for(base_url: str) -> Provider | None:
    return next((p for p in PROVIDERS if p.base_url and p.base_url == base_url.rstrip("/")), None)
