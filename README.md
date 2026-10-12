# Penwise

Select text in any app on your Mac, press **⌃⌥P**, and see what's wrong with your English, with a short
explanation of each change. Keep the changes you agree with, press **Return**, and your text is replaced.

Penwise is made for research and professional writing by non-native speakers. It aims to teach as well as correct:
every change comes with a short note, and the fixes you make again and again show up in `penwise insights`.

It is built to work with a small local model (such as a 1B model on an M1 Mac) or any cloud model you have an API key for.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/panel-dark.png">
  <img src="docs/panel-light.png" width="640" alt="The Penwise review panel: the text with each change marked, and a list of the changes with a label and a short note for each.">
</picture>

## How it works

```
 Any Mac app (text selected)
        │  ⌃⌥P fix  ·  ⌃⌥⇧P improve
        ▼
 Hammerspoon Spoon (Lua)          reads the selection, shows the review panel, pastes the result
        │  stdin → JSON lines
        ▼
 penwise (Python)
   engine.py    split into paragraphs → ask the model → clean reply → sanity-check → diff
   prompts.py   short prompts with examples, tuned on 1B models
   llm.py       one client for every model: the OpenAI-compatible chat API
   diff.py      word-level diff, computed in code, not by the model
   lessons.py   a label and a fixed teaching note for each change
   history.py   a local log of accepted fixes → "you've made this fix 3× before"
        │  HTTP
        ▼
 Ollama / LM Studio / llama.cpp / MLX on your Mac   — or —   OpenAI / OpenRouter / Groq / …
```

Three design rules keep it trustworthy:

- **The model only rewrites; Penwise works out the changes.** The list of changes is computed by diffing your text
  against the model's version, so what you see is exactly what will change. You can undo any single change.
- **If the model replies to your text instead of editing it, Penwise doesn't use that reply.** Small models sometimes
  answer a question in your text, or rewrite it completely. Penwise checks each reply and, if it doesn't look like an
  edit of your text, leaves that part unchanged and tells you.
- **Explanations are written in advance, not generated.** Each change gets a label (Articles, Prepositions, Word
  form, Commonly confused, …) and a fixed note. You can also ask the model for a one-line reason per change, but this
  is off by default because 1B models often give wrong ones.

## Quick start (macOS)

1. **Get a local model.** Install [Ollama](https://ollama.com), then:

   ```sh
   ollama pull gemma3:1b
   ```

2. **Install Penwise** with [uv](https://docs.astral.sh/uv/) (`brew install uv`) or pipx:

   ```sh
   uv tool install git+https://github.com/LuckyLetter/penwise
   penwise init      # writes ~/.config/penwise/config.toml
   penwise doctor    # checks the setup and runs a test sentence
   ```

3. **Add the hotkey** with [Hammerspoon](https://www.hammerspoon.org), a free, open-source macOS automation app:

   ```sh
   brew install --cask hammerspoon
   penwise setup-mac
   ```

   Then open Hammerspoon, choose **Reload Config** from its menu bar icon, and allow it under
   **System Settings → Privacy & Security → Accessibility**.

4. **Use it.** Select text anywhere and press **⌃⌥P** to fix it, or **⌃⌥⇧P** to also improve clarity and flow.

| In the panel   |                                   |
| -------------- | --------------------------------- |
| click / 1–9    | undo or redo a single change      |
| Return         | replace your selection            |
| ⌘C             | copy the result instead           |
| Tab            | switch between Fix and Improve    |
| Esc            | close without changing anything   |

## Choosing a model

Every model is reached the same way, through an OpenAI-compatible chat API, so switching is a matter of changing
`base_url` and `model` in `~/.config/penwise/config.toml`:

| Where                 | `base_url`                      | `model` (example)                         |
| --------------------- | ------------------------------- | ----------------------------------------- |
| Ollama (default)      | `http://localhost:11434/v1`     | `gemma3:1b`, `llama3.2:1b`                |
| LM Studio             | `http://localhost:1234/v1`      | the model id shown in LM Studio           |
| MLX (`mlx_lm.server`) | `http://localhost:8080/v1`      | `mlx-community/Llama-3.2-1B-Instruct-4bit` |
| A cloud service       | the service's OpenAI-compatible URL, e.g. `https://api.openai.com/v1` | a model from that service |

**About 1B models:** they catch common errors well (verb agreement, articles, prepositions, spelling, *then/than*).
They miss some errors and now and then over-edit, which is why every change can be undone. The prompts were tuned
on `gemma3:1b` and `llama3.2:1b`; `gemma3:1b` caught slightly more errors. A larger local model or a cloud model
gives better corrections, and its one-line explanations are worth turning on (`explain = true`).

**API keys** for cloud services: keep them in the macOS Keychain rather than in a file.

```sh
security add-generic-password -a "$USER" -s penwise -w      # paste your key when asked
```

```toml
# ~/.config/penwise/config.toml
base_url = "https://api.openai.com/v1"
model = "a-model-name-from-your-provider"
api_key_command = "security find-generic-password -s penwise -w"
```

`api_key_env = "SOME_VAR"` and `api_key = "..."` also work. Local servers need no key.

## Configuration

`penwise init` writes a commented config file. All settings:

| Setting           | Default                     | Meaning                                                        |
| ----------------- | --------------------------- | -------------------------------------------------------------- |
| `base_url`        | `http://localhost:11434/v1` | OpenAI-compatible API to use                                   |
| `model`           | `gemma3:1b`                 | model name at that API                                         |
| `api_key_command` | –                           | shell command that prints the API key (e.g. from the Keychain) |
| `api_key_env`     | –                           | environment variable holding the API key                       |
| `api_key`         | –                           | the API key itself (least safe)                                |
| `mode`            | `fix`                       | `fix`: only errors · `improve`: also clarity and flow          |
| `explain`         | `false`                     | also ask the model for a one-line reason per change            |
| `history`         | `true`                      | keep a local log of accepted changes for `penwise insights`    |
| `temperature`     | `0.2`                       | lower is more predictable                                      |
| `timeout`         | `60`                        | seconds to wait for the model                                  |

## Learning from your changes

```console
$ penwise insights
42 accepted changes since 2026-10-12

What you fix most:
    14  Articles
     9  Prepositions
     7  Word form

Fixes you've made more than once:
     5× in → on
         e.g. …results [in] the other hand…
```

The review panel also tells you when you've made the same fix before. History is a plain JSON Lines file at
`~/.local/share/penwise/history.jsonl`; `penwise history --clear` deletes it, and `history = false` turns it off.

## Privacy

- Your text is sent **only** to the `base_url` you configure. With a local model, nothing leaves your Mac.
- Penwise stores your config, plus (unless turned off) the accepted changes: the changed words and up to a few
  words on each side, never whole texts.
- No telemetry, no accounts, no network calls besides the model API.
- Hammerspoon needs Accessibility permission to copy your selection and paste the result. Penwise puts your
  clipboard back afterwards.

## In the terminal

The panel is optional; `penwise check` works anywhere, including Linux:

```sh
penwise check "We evaluate our approach on three benchmark."   # changes with notes
pbpaste | penwise check -f text | pbcopy                         # just the corrected text
penwise check -m improve -f json < draft.txt                     # everything, as JSON
```

**No Hammerspoon?** In Automator, create a *Quick Action* that receives text in any application, add *Run Shell
Script* with `~/.local/bin/penwise check -f text`, tick *Output replaces selected text*, and give it a shortcut in
System Settings → Keyboard → Keyboard Shortcuts → Services. You get the corrected text, without the review panel.

## Limitations

- Each paragraph is checked separately, so the model doesn't see the rest of your document.
- LaTeX, Markdown and citations are usually kept as they are, but small models occasionally touch them. Check the
  changes on technical text.
- A few apps don't allow reading or pasting text this way. Use ⌘C in the panel and paste yourself.

## Development

```sh
git clone https://github.com/LuckyLetter/penwise && cd penwise
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m playwright install chromium   # optional: enables the panel tests
ruff check . && ruff format --check . && pytest
```

The tests start a fake OpenAI-compatible server, so no model is needed. `tests/test_spoon.py` runs the Hammerspoon
Spoon in an embedded Lua interpreter with stubbed `hs` APIs, and `tests/test_panel.py` drives the review panel in a
headless browser.

## License

[Apache 2.0](LICENSE)
