# Penwise

Click in any text box on your Mac and press **⌃⌥P**. Penwise shows what's wrong with your English, with a short
explanation of each change. Press **Return**, and your text is fixed.

Penwise is made for research and professional writing by non-native speakers. It aims to teach as well as correct:
every change comes with a short note, and the fixes you make again and again show up in `penwise insights`.

It works with a cloud model you have an API key for, or a small local model (such as a 1B model on an M1 Mac).
Setup is one download: open it, choose a model, and you're done.

**What it does**

- **Fixes your English anywhere on your Mac.** Press **⌃⌥P** in any text box, review the changes right
  next to your text, press Return. No copying and pasting, and usually no selecting either.
- **Teaches as it fixes.** Every change has a label (Articles, Subject–verb agreement, Possessives, …) and a short
  rule; *Your recurring fixes* shows the rules you need most often, each with an example from your own writing.
- **Fills in what you can't say yet.** Write a phrase in your own language or as `[[your idea]]`, or leave
  `[[?]]` where you can't find the word, and Penwise writes it in English.
- **Safe and in your control.** It never changes numbers, citations, acronyms, math, code or links on its own; you
  can undo any single change; with a local model nothing leaves your Mac.
- **Simple to set up.** One download installs everything, with nothing to type; then you choose a model in the
  window that opens.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/panel-dark.png">
  <img src="docs/panel-light.png" width="640" alt="The Penwise review panel: the text with each change marked, and a list of the changes with a label and a short note for each.">
</picture>

## How it works

```
 Any Mac app (a text box, a selection, or the paragraph at the cursor)
        │  ⌃⌥P fix  ·  ⌃⌥⇧P improve  ·  ⌃⌥⌘P quick fix
        ▼
 Hammerspoon Spoon (Lua)          reads the text, shows the review panel at it, pastes the result
        │  text as an argument → JSON lines
        ▼
 penwise (Python)
   engine.py    split into paragraphs → ask the model (in parallel) → clean → sanity-check → diff
   prompts.py   short prompts with examples, tuned on 1B models
   llm.py       one client for every model: the OpenAI-compatible chat API
   diff.py      word-level diff, computed in code, not by the model
   lessons.py   a label and a fixed teaching note for each change
   history.py   a local log of accepted fixes → "you've made this fix 3× before"
   wizard.py    `penwise setup`: model, key (Keychain), hotkey, all in one go
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

1. **Download [Install Penwise](https://github.com/LuckyLetter/penwise/releases/latest/download/Install-Penwise.zip)
   and open it.** It installs Penwise and [Hammerspoon](https://www.hammerspoon.org), the free app that gives
   Penwise its shortcut, in a minute or two.

   The first time, macOS says it can't check the app, because it isn't signed by an Apple developer yet. Click
   **Done**, open **System Settings → Privacy & Security**, scroll down, and click **Open Anyway** next to
   *Install Penwise*.

2. **Choose a model** in the Penwise window that opens: *On this Mac* (free and private, in
   [Ollama](https://ollama.com); Save starts it and downloads the model, unless you have one already) or *API*
   (paste your key: for OpenRouter, OpenAI, Anthropic, Groq, Gemini and xAI keys Penwise fills in the address; the
   key goes in the macOS Keychain). Save tests it right away.
   When macOS asks, turn on Hammerspoon under **Accessibility**: that lets Penwise read and replace your text.

3. **Use it.** Click in any text box and press **⌃⌥P** (Control+Option+P). Look over the changes, then press
   **Return** to put the fix in, or **Esc** to close. That's all you need to know.

When you want more:

| Key | What it does |
| --- | ------------ |
| click a change, or 1–9 | undo or redo that change |
| Tab | switch between *Fix* and *Improve* (clarity and flow) |
| ⌘C | copy the result instead of replacing |
| **⌃⌥⇧P** | open straight in *Improve* |
| **⌃⌥⌘P** | quick fix: replace right away, with a one-line summary |

Prefer clicking? The **✎ icon in the menu bar** has the same three actions, plus *Your recurring fixes*,
*Try it on a practice note* (handy for showing a colleague; also `penwise try`), *Settings* (model, API key and
shortcut), *Check my setup*, and *Uninstall Penwise*.

**You rarely need to select anything.** With nothing selected, Penwise reads the text straight from the app: in a
short text box (a message, a comment, up to 2,000 characters) it takes the whole box; in a longer document, the
paragraph your cursor is in. Select text to check just that. The panel opens right above your text, sized to fit,
and closes by itself when your text needs no changes, or when you click elsewhere. Another app uses ⌃⌥P? Pick another
letter under *Shortcut* in Settings. To change the keys around it, edit the Penwise block in
`~/.hammerspoon/init.lua`; running `penwise setup` again keeps your changes.

### The right tone, automatically

*Improve* adapts to where you're writing: in Mail or Outlook it keeps an email polite and professional; in Slack,
Teams, Messages, WeChat, Feishu or DingTalk it stays friendly and natural instead of turning formal; everywhere else it aims for
research writing. In a browser, the tab title decides (Gmail counts as email, Overleaf as research). The panel shows
the tone next to the mode; click *Research*, *Email* or *Chat* to change it. In the terminal, use
`penwise check -m improve --style email|chat|academic`. *Fix* only corrects errors and keeps your tone everywhere.

### Safe by default

Changes that would alter a **number, citation, acronym, formula, code or link** are shown but not applied: the
model can't check those, and small models sometimes drop a `[12]` or expand "LLMs". Click such a change to apply
it anyway. If the model keeps "fixing" a name or a term (say, `Pytorch`), click **Always keep “Pytorch”** under the
change, or run `penwise keep Pytorch`; `penwise keep` lists the words you keep.

### Not sure how to say it? Leave it to Penwise

Write the part you're unsure about in your own language, or as a note in double brackets, or leave `[[?]]` where
you can't find the word, and check as usual:

```text
In this paper, 我们提出 a new method for 图像分割.           →  In this paper, we propose a new method for image segmentation.
The results [[show very clear]] that the model is robust.  →  The results clearly show that the model is robust.
We [[want to say: did not have enough time]] to test more. →  We did not have enough time to test more.
Thank you for your quick reply, I [[?]] it.                →  Thank you for your quick reply, I appreciate it.
```

Penwise notices these by itself (any non-Latin script, or `[[…]]`) and fills in the English. Each filled-in part
appears as its own change, so you can learn the phrase, and undo it if the translation is off. Citations like
`[12]` are left alone.

**Updating:** when a new version is out, the ✎ icon shows a dot (✎•); *Update Penwise* in its menu downloads it and
restarts Penwise, with no Terminal. Opening the newest *Install Penwise* works too; your settings and hotkeys stay as
they are.
If something isn't working, *Check my setup* in the ✎ menu checks each part and says what to do.

**Uninstalling:** *Uninstall Penwise…* in the ✎ menu removes the hotkey, your settings, API key and history, and
Penwise itself; if Install Penwise put Hammerspoon there for it, Hammerspoon can go to the Trash too. In the
Terminal: `penwise uninstall`. uv and the Python it downloaded stay, as other apps may use them.

**Prefer the Terminal?** Install with [uv](https://docs.astral.sh/uv/) and run the guided setup, which asks the same
questions and downloads Hammerspoon if needed:

```sh
uv tool install git+https://github.com/LuckyLetter/penwise
uv tool update-shell    # then open a new Terminal window
penwise setup
```

Installed this way, `penwise update` gets the latest version and refreshes the hotkey. Once a day Penwise looks for
a new version; when there is one, the menu bar icon shows a dot (✎•) and its menu offers *Update Penwise*.

## Choosing a model

See the model in use and some suggestions, or switch (Penwise tests the new model before saving it):

```sh
penwise model
penwise model mistralai/mistral-small-2603
```

Every model is reached the same way, through an OpenAI-compatible chat API, so any of these work. In Settings,
*On this Mac* uses Ollama, and for *API* a pasted OpenRouter, OpenAI, Anthropic, Groq, Gemini or xAI key fills in the
address by itself (`penwise setup` does the same in the Terminal).

| Where                 | `base_url`                      | `model` (example)                         |
| --------------------- | ------------------------------- | ----------------------------------------- |
| Ollama (default)      | `http://localhost:11434/v1`     | `gemma3:1b`, `llama3.2:1b`                |
| LM Studio             | `http://localhost:1234/v1`      | the model id shown in LM Studio           |
| MLX (`mlx_lm.server`) | `http://localhost:8080/v1`      | `mlx-community/Llama-3.2-1B-Instruct-4bit` |
| OpenRouter (one key, many cloud models) | `https://openrouter.ai/api/v1` | an id from openrouter.ai/models, e.g. `mistralai/mistral-small-2603` |
| Another cloud service | the service's OpenAI-compatible URL, e.g. `https://api.openai.com/v1` | a model from that service |

**About 1B models:** they catch common errors well (verb agreement, articles, prepositions, spelling, *then/than*).
They miss some errors and now and then over-edit, which is why every change can be undone. The prompts were tuned
on `gemma3:1b` and `llama3.2:1b`; `gemma3:1b` caught slightly more errors. A larger local model or a cloud model
gives better corrections, and its one-line explanations are worth turning on (`explain = true`).

**Speed:** many cloud models "think" before answering, which adds seconds to every check. For the models it
suggests, Penwise turns that down automatically (`reasoning_effort`). For a hotkey tool, a fast model that doesn't
think by default, like `mistralai/mistral-small-2603`, feels best.

**API keys:** Settings (and `penwise setup`) store the key in the macOS Keychain and points the config at it with
`api_key_command = "security find-generic-password -s penwise -w"`. `api_key_env = "SOME_VAR"` and
`api_key = "..."` also work. Local servers need no key.

## Configuration

`penwise config` shows your settings, and `penwise config set <name> <value>` changes one (for example
`penwise config set explain true`). The file is `~/.config/penwise/config.toml`; `penwise init` writes a version
with every setting explained. All settings:

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
| `reasoning_effort`| –                           | how long a cloud model "thinks" first (`none`, `low`, …); lower is faster |
| `keep`            | `[]`                        | words Penwise never changes (`penwise keep <word>`)            |

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
- Penwise stores your config, your API key in the Keychain, and (unless turned off) the accepted changes: the
  changed words and up to a few words on each side, never whole texts.
- No telemetry, no accounts. Besides the model API, Penwise goes online only to set itself up (uv, Python and
  Hammerspoon) and to look for updates.
- Hammerspoon needs Accessibility permission to read the text you're checking and paste the result. Penwise
  puts your clipboard back afterwards.

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

## Tested apps

Tested on a Mac with Notes, Visual Studio Code, Claude, Codex, WeChat, Chrome (the address bar and boxes in web
pages, such as Google's search box) and Terminal (shell commands, and prompts in Claude Code), also with apps in
full screen. Other apps work the same way when they let other apps read their text boxes; if one doesn't,
*Check my setup* in the ✎ menu shows what the hotkey did there.

## Limitations

- Each paragraph is checked separately, so the model doesn't see the rest of your document.
- LaTeX, Markdown and citations are usually kept as they are, but small models occasionally touch them. Check the
  changes on technical text.
- A few apps don't allow reading or selecting text this way. When Penwise can't select your original text to
  replace it, it doesn't paste next to it: it copies the fix and tells you, so you can select the text and press ⌘V.
- In a terminal (Terminal, iTerm2, Warp, …), Penwise checks what you're typing: the command after the prompt, or
  the prompt in Claude Code's or Codex's input box (or the text you select). Replace clears that line (⌃E ⌃U) and
  pastes the fix. For text you can't edit, like a web page, the button says *Copy*.
- Some apps (WeChat, Codex, …) don't let other apps read their text boxes. There Penwise selects all in the box
  and copies it, as you would by hand, and Replace selects all again and pastes.
- If the hotkey doesn't do what you expect, choose *Check my setup* in the ✎ menu (`penwise doctor` in the
  Terminal): it ends with what the hotkey did, step by step (the app, the kind of text box, what was selected and
  pasted, and whether the whole fix arrived; never your text).

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
headless browser. On a macOS runner, CI also runs `tests/test_macos.py`: it stores a key in a real (temporary)
Keychain, and drives the review panel and quick fix inside the real Hammerspoon app.

**The installer:** `python installer/build.py` writes `dist/Install-Penwise.zip`: an app that runs
`installer/install.sh` with this version of Penwise inside. To publish a version, run the *Release* workflow
(Actions → Release → Run workflow, or push a tag like `v0.7.0`): it builds the zip and attaches it to a release named
after the version, and the download link above always points to the latest release.

## License

[Apache 2.0](LICENSE)
