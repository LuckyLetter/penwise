# Penwise

**English** · [中文](docs/readme/zh.md) · [日本語](docs/readme/ja.md) · [한국어](docs/readme/ko.md)

Better English in any text box on your Mac: press **⌃⌥P**, check the changes, press **Return**.

<img src="docs/demo.gif" width="640" alt="Penwise in a text box: ⌃⌥P shows the fixes, Tab switches to Improve, and Return puts the text in place.">

- **Fixes your English anywhere**: mail, chat, documents, the browser. No copying and pasting.
- **Teaches as it fixes**: every change comes with a short note on the rule.
- **Fills in what you can't say yet**: write a word in your own language, or `[[?]]`, and Penwise finds the English.
- **Safe**: it never changes numbers, citations, code or links on its own, and you can undo any change.

## Install

1. Download **[Penwise.dmg](https://github.com/LuckyLetter/penwise/releases/latest/download/Penwise.dmg)**, open it,
   and drag Penwise to Applications. Open it from there.
   - If macOS says it can't check the app: click **Done**, open **System Settings → Privacy & Security**, and click
     **Open Anyway**.
2. In the window that opens, enter your AI provider's **API Endpoint**, **API Key** and **Model**, and press **Save**.
   - **Not sure which? We recommend [OpenRouter](https://openrouter.ai) with `openai/gpt-oss-20b`**: fast, and
     nearly free (a dollar covers more than ten thousand checks). Create a key at
     [openrouter.ai](https://openrouter.ai/settings/keys) and add a little credit, copy the key, and click in the
     API Key box: the key and the API Endpoint fill themselves in. Then type `openai/gpt-oss-20b` as the Model.
   - Rather keep your text on your Mac? Use a free model there: [Ollama](docs/GUIDE.md#a-model-on-your-mac-ollama).
3. When macOS asks, turn on **Hammerspoon** under **Accessibility**: that lets Penwise read and replace your text.

## Use

Click in any text box and press **⌃⌥P**. Press **Return** to put the fix in, or **Esc** to close.

| Keys | What it does |
| ---- | ------------ |
| **⌃⌥P** | fix the errors |
| **⌃⌥⇧P** | also improve clarity and flow |
| **⌃⌥⌘P** | fix right away, without the panel |

Everything else is in Penwise's menu, the pen nib in the menu bar: *Settings*, *Your recurring fixes*, *Check my
setup*, *Update* and *Uninstall*.

## Language

Penwise speaks English, 中文, 日本語 and 한국어: choose yours at the top of **Settings**. Your text is always checked as
English.

## More

[The guide](docs/GUIDE.md): models, privacy, the Terminal, troubleshooting, and how Penwise works.

[Apache 2.0](LICENSE)
