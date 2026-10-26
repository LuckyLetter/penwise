# Penwise guide

[← Back to the README](../README.md)

## Installing

Download [Penwise.dmg](https://github.com/LuckyLetter/penwise/releases/latest/download/Penwise.dmg), open it, drag
*Penwise* onto *Applications*, and open it from there. (Opened straight from the disk image, it offers to move itself
there.) Everything it needs is inside (21 MB, for Apple and Intel Macs, macOS 13 or later), so it sets itself up in a
few seconds with nothing more to download. [Hammerspoon](https://www.hammerspoon.org), the free app that gives Penwise
its shortcut, comes with it; if you have Hammerspoon already, Penwise uses yours.

Until Penwise is signed by an Apple developer, the first time macOS says it can't check the app: click **Done**, open
**System Settings → Privacy & Security**, scroll down, and click **Open Anyway** next to *Penwise*. If macOS says
instead that the app *is damaged*, it is the same missing signature: paste `xattr -cr /Applications/Penwise.app` in
Terminal, press Return, and open it again.

In the window that opens, put in your AI provider's **API Endpoint** (any URL from its API examples works), your
**API Key** if it needs one, and the **Model** name. **Save** tests it right away. Not sure which? We recommend
[OpenRouter](https://openrouter.ai) with `openai/gpt-oss-20b`: it answers fast and costs very little (at today's
prices, a dollar covers more than ten thousand checks; add a little credit to your OpenRouter account first). For a service in the cloud, copy
your key from its website, then click in the API Key box: the key fills itself in, and for OpenRouter, OpenAI,
Anthropic, Groq, Gemini and xAI so does the API Endpoint; the Model box lists the service's models. The key is kept in
your Mac's Keychain. When macOS asks, turn on Hammerspoon under **Accessibility**: that lets Penwise read and replace
your text.

## Using it

Click in any text box and press **⌃⌥P** (Control+Option+P). Look over the changes, then press **Return** to put the
fix in, or **Esc** to close. That's all you need to know.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="panel-dark.png">
  <img src="panel-light.png" width="640" alt="The Penwise panel: your text with each change marked, and a short note for each change.">
</picture>

When you want more:

| Key | What it does |
| --- | ------------ |
| click a change, or 1–9 | undo or redo that change |
| Tab | switch between *Fix* and *Improve* (clarity and flow) |
| ⌘C | copy the result instead of replacing |
| **⌃⌥⇧P** | open straight in *Improve* |
| **⌃⌥⌘P** | quick fix: replace right away, with a one-line summary |

Prefer clicking? **Penwise's pen nib in the menu bar** has the same three actions, plus *Your recurring fixes*,
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

## Updating and uninstalling

**Updating:** when a new version is out, the pen nib in the menu bar shows a dot; *Update Penwise* in its menu downloads it and
restarts Penwise, with no Terminal. Putting the newest Penwise in Applications in place of the old one works too;
your settings and hotkeys stay as they are. Opening Penwise from Applications opens its settings.
If something isn't working, *Check my setup* in Penwise's menu checks each part and says what to do.

**Uninstalling:** *Uninstall Penwise…* in Penwise's menu removes Penwise and everything it put on your Mac: the
shortcut, your settings, API key and history, the app and its place in the Dock, and the Hammerspoon it set up, with Hammerspoon's settings and
its Accessibility permission. If you had Hammerspoon before Penwise, it stays as it was. In the Terminal:
`penwise uninstall`. Dragging Penwise to the Trash works too: its shortcut and menu go with it, and your settings
stay, as other apps' do, for when you put it back.

## Installing in the Terminal

Prefer the Terminal? Install with [uv](https://docs.astral.sh/uv/) and run the guided setup, which asks the same
questions and downloads Hammerspoon if needed:

```sh
uv tool install git+https://github.com/LuckyLetter/penwise
uv tool update-shell    # then open a new Terminal window
penwise setup
```

Installed this way, `penwise update` gets the latest version and refreshes the hotkey. Once a day Penwise looks for
a new version; when there is one, the menu bar icon shows a dot and its menu offers *Update Penwise*.

## Language

Penwise's windows, menu and notes come in English, 中文 (Chinese), 日本語 (Japanese) and 한국어 (Korean): choose one
at the top of **Settings**, and the window changes at once. With a cloud model, the one-line reasons for each change
come in that language too. Your text is always checked as English. In the Terminal: `penwise config set language zh`.

**Adding a language** takes one file: copy `src/penwise/hammerspoon/Penwise.spoon/locales/zh.json` to
`<code>.json` (say `fr.json`), set its `name` (the language in itself, as the settings list it), `tag` and
`model_name`, and translate the texts in `strings`, keeping each `{name}` in it. Penwise finds the file by itself;
`pytest tests/test_i18n.py` says what is missing, and `python tests/test_i18n.py` lists every text. The README in
that language, if you like, is `docs/readme/<code>.md`, with its name added to the line of languages at the top of
`README.md`.

## Choosing a model

See the model in use and some suggestions, or switch (Penwise tests the new model before saving it):

```sh
penwise model
penwise model mistralai/mistral-small-2603
```

Every model is reached the same way, through an OpenAI-compatible chat API, so any of these work: in Settings, put
in the API endpoint, the key if the service needs one, and the model. A pasted OpenRouter, OpenAI, Anthropic, Groq,
Gemini or xAI key fills in the endpoint by itself (`penwise setup` does the same in the Terminal).

### A model on your Mac (Ollama)

Free, and your text never leaves your Mac.

1. Download [Ollama](https://ollama.com/download) and open it.
2. Download a model: choose one in Ollama's window and send it a message, or in the Terminal run, for example,
   `ollama pull gemma3:1b` (small and quick, fine on an 8 GB Mac).
3. In Penwise's settings, click `http://localhost:11434/v1` under the API endpoint box (or type it), leave the key empty,
   type the model's name (`gemma3:1b`; the models Ollama has come up as you click in the box), and press **Save**.

Penwise starts Ollama when it isn't running, and Save downloads the model if Ollama doesn't have it yet.

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

**Speed:** many models "think" before answering, which can add ten seconds or more to every check; Penwise itself
takes a fraction of a second. When you press Save, Penwise finds how to ask your model to think little or not at all,
tries it, and remembers what works (`less_thinking` in `penwise config`). On OpenRouter it goes by OpenRouter's own
list of each model's settings; elsewhere by each service's documented setting, for OpenAI's thinking models (GPT-5,
o-series, and gpt-oss on OpenAI, on Groq, or on your Mac in LM Studio 0.4.8 or later or Ollama), Gemini, Qwen
(DashScope), GLM (Zhipu) and Doubao (Volcengine). A model that refuses it is used as it is. (gpt-oss can't stop
thinking; it thinks little.) If the test after Save is still slow, the settings say so: choose a model that doesn't
think, such as `deepseek-chat` rather than `deepseek-reasoner`, or `mistralai/mistral-small-2603` on OpenRouter. A
service far away, or busy, adds its own delay.

**API keys:** Settings (and `penwise setup`) store the key in the macOS Keychain and point the config at it with
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
| `language`        | `en`                        | of Penwise's windows and notes: `en`, `zh`, `ja`, `ko`         |
| `explain`         | `false`                     | also ask the model for a one-line reason per change            |
| `history`         | `true`                      | keep a local log of accepted changes for `penwise insights`    |
| `temperature`     | `0.2`                       | lower is more predictable                                      |
| `timeout`         | `60`                        | seconds to wait for the model                                  |
| `keep`            | `[]`                        | words Penwise never changes (`penwise keep <word>`)            |

## Learning from your changes

*Your recurring fixes* in Penwise's menu shows your most common mistake at the top, then a bar for each kind of fix
you make, and the rule for the one you pick (click a bar, or press ↑ ↓) with a fix from your own writing. Below are
the fixes you keep making. Only mistakes count: rewordings from Improve, and words Penwise filled in for you, don't.
In the Terminal:

```console
$ penwise insights
42 fixes since 2026-10-12

What you fix most:
    14  Articles
     9  Subject–verb agreement   e.g. …each of the models [are] tested…
     7  Prepositions

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
*Check my setup* in Penwise's menu shows what the hotkey did there.

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
- If the hotkey doesn't do what you expect, choose *Check my setup* in Penwise's menu (`penwise doctor` in the
  Terminal): it ends with what the hotkey did, step by step (the app, the kind of text box, what was selected and
  pasted, and whether the whole fix arrived; never your text).

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
   lessons.py   a label and a fixed teaching note for each change, naming the grammar rule
   history.py   a local log of accepted fixes → "Your recurring fixes", "you've made this fix 3× before"
   settings.py  the settings window: model, key (Keychain), Ollama started, models listed
   wizard.py    `penwise setup`: the same, in the Terminal
   setup_mac.py the hotkey: Hammerspoon (downloaded if needed) and the Spoon
   updater.py   updates; uninstall.py removes it all  ·  installer/  Install Penwise.app
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

**The app:** `python installer/build_app.py` writes `dist/Penwise.dmg`, a disk image to drag Penwise into
Applications from, compressed with LZMA: Penwise.app with Python (a program for Apple and one for Intel Macs, sharing
one library), Penwise, and Hammerspoon inside, the two scripts in `installer/app/` that set it up and run it, and its
icon (`installer/app/make_icon.py` draws it). On a Mac it uses `hdiutil`; on Linux, `mkfs.hfsplus` (hfsprogs) and the
`hfsplus` and `dmg` tools of [libdmg-hfsplus](https://github.com/mozilla/libdmg-hfsplus) (see the Release workflow
for how to build them), with `PENWISE_DMG_TOOLS` saying where they are; without them it writes `dist/Penwise.zip`
instead (`--zip` writes both). On a Mac, `PENWISE_SIGN_IDENTITY` (a *Developer ID
Application* certificate) signs it and `PENWISE_NOTARY_PROFILE` (from `xcrun notarytool store-credentials`) has Apple
notarize it, so it opens without the Privacy & Security step; the Release workflow does the same on a Mac when the
repository has the secrets named in `.github/workflows/release.yml`. To publish a version, run the *Release* workflow (Actions → Release → Run
workflow, or push a tag like `v0.7.0`): it builds them and attaches them to a release named after the version, and the
download link above always points to the latest release.
