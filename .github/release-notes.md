**Better English in any text box on your Mac:** press **⌃⌥P**, check the changes, press **Return**.

**New in 1.0.1:** *Your recurring fixes* shows at a glance which mistake you make most, with a bar for each kind of
fix and the rule to remember. Already have Penwise? Choose *Update Penwise* in its menu.

![Penwise in a text box: ⌃⌥P shows the fixes, Tab switches to Improve, and Return puts the text in place.](https://github.com/LuckyLetter/penwise/raw/main/docs/demo.gif)

## Install

1. Download **Penwise.dmg** below (21 MB, for Apple silicon and Intel Macs, macOS 13 or later), open it, and drag
   Penwise to Applications. Open it from there.
2. In the window that opens, enter your AI provider's **API Endpoint**, **API Key** and **Model**, and press **Save**.
   - **Not sure which? We recommend [OpenRouter](https://openrouter.ai) with `openai/gpt-oss-20b`**: fast, and nearly
     free (a dollar covers more than ten thousand checks). Create a key at
     [openrouter.ai](https://openrouter.ai/settings/keys) and add a little credit, copy the key, and click in the API
     Key box: the key and the API Endpoint fill themselves in. Then type `openai/gpt-oss-20b` as the Model.
   - Rather keep your text on your Mac? Use a free model there with
     [Ollama](https://github.com/LuckyLetter/penwise/blob/main/docs/GUIDE.md#a-model-on-your-mac-ollama).
3. When macOS asks, turn on **Hammerspoon** under **Accessibility**: that lets Penwise read and replace your text.

> **The first time you open it,** macOS says it can't check the app, because Penwise isn't signed by an Apple
> developer yet. Click **Done**, open **System Settings → Privacy & Security**, scroll down, and click **Open Anyway**
> next to Penwise. If macOS says instead that the app *is damaged*, it's the same missing signature: paste
> `xattr -cr /Applications/Penwise.app` in Terminal, press Return, and open it again.

## What it does

- **Fixes your English anywhere:** mail, chat, documents, the browser, even the Terminal. No copying and pasting:
  Penwise reads the text box, and Return puts the fix in its place.
- **Fix or Improve:** ⌃⌥P fixes the errors; Tab (or ⌃⌥⇧P) also improves clarity and flow, in the right tone for an
  email, a chat or research writing. ⌃⌥⌘P fixes right away, without the panel.
- **Teaches as it fixes:** every change comes with a short note on the rule, and *Your recurring fixes* shows the
  mistake you make most, with a bar for each kind and the rule to remember.
- **Fills in what you can't say yet:** write a word in your own language, or `[[?]]`, and Penwise finds the English.
- **Safe:** it never changes numbers, citations, code or links on its own, and you can undo any single change.
- **In your language:** the window, menu and notes come in English, 中文, 日本語 or 한국어 (top of Settings).
- **Private:** your text goes only to the model you choose; with a model on your Mac, nothing leaves it. The API key is
  kept in your Mac's Keychain. No accounts, no tracking.
- **Looks after itself:** a dot on Penwise's menu bar icon says when an update is ready; *Update Penwise* installs it.
  *Uninstall Penwise…* removes everything it put on your Mac.

## Good to know

- Some apps (WeChat, for example) don't let other apps read their text boxes. There Penwise selects and copies the
  text itself, as you would. When it can't put the fix back safely, it copies the fix and tells you, so you can paste
  it with ⌘V.
- Small models on your Mac (1B) are free and private, but miss some errors. A cloud model catches more.
- Something not working? Choose *Check my setup…* in Penwise's menu: it checks each part and says what to do. Then
  [open an issue](https://github.com/LuckyLetter/penwise/issues) with what it says.

More in the [guide](https://github.com/LuckyLetter/penwise/blob/main/docs/GUIDE.md): models, privacy, the Terminal,
and how Penwise works.

<details>
<summary><b>中文</b></summary>

在 Mac 上的任何输入框里写出更好的英文：按 **⌃⌥P**，看一下修改，按 **Return**。

1. 下载下方的 **Penwise.dmg**，打开后把 Penwise 拖到“应用程序”，再从那里打开。
2. 在打开的窗口里填写 AI 服务商的 **API 端点**、**API 密钥** 和 **模型**，然后点 **保存**。不知道选哪个？推荐
   [OpenRouter](https://openrouter.ai) 的 `openai/gpt-oss-20b`：速度快，几乎免费。
3. macOS 询问时，在 **辅助功能** 里打开 **Hammerspoon**。

第一次打开时，macOS 会提示无法验证这个 App：点 **完成**，打开 **系统设置 → 隐私与安全性**，点 **仍要打开**。
界面语言可以在 **设置** 顶部选择中文。[中文说明](https://github.com/LuckyLetter/penwise/blob/main/docs/readme/zh.md)

</details>

<details>
<summary><b>日本語</b></summary>

Mac のどの入力欄でも、より良い英語を：**⌃⌥P** を押して、変更を確認し、**Return** を押すだけ。

1. 下の **Penwise.dmg** をダウンロードして開き、Penwise をアプリケーションフォルダにドラッグします。そこから開いてください。
2. 開いたウインドウに、AI サービスの **API エンドポイント**、**API キー**、**モデル** を入力し、**保存** を押します。
   おすすめは [OpenRouter](https://openrouter.ai) の `openai/gpt-oss-20b` です：速く、ほぼ無料です。
3. macOS に聞かれたら、**アクセシビリティ** で **Hammerspoon** をオンにします。

初めて開くとき、macOS がアプリを確認できないと表示したら：**完了** をクリックし、**システム設定 → プライバシーと
セキュリティ** で **このまま開く** をクリックします。表示言語は **設定** の上部で日本語を選べます。
[日本語の説明](https://github.com/LuckyLetter/penwise/blob/main/docs/readme/ja.md)

</details>

<details>
<summary><b>한국어</b></summary>

Mac의 어느 입력란에서나 더 나은 영어로: **⌃⌥P**를 누르고, 수정 내용을 확인한 뒤, **Return**을 누르세요.

1. 아래의 **Penwise.dmg**를 내려받아 열고, Penwise를 응용 프로그램 폴더로 드래그한 뒤 거기서 여세요.
2. 열린 창에 AI 서비스의 **API 엔드포인트**, **API 키**, **모델**을 입력하고 **저장**을 누르세요.
   추천: [OpenRouter](https://openrouter.ai)의 `openai/gpt-oss-20b` — 빠르고 거의 무료입니다.
3. macOS가 물어보면 **손쉬운 사용**에서 **Hammerspoon**을 켜세요.

처음 열 때 macOS가 앱을 확인할 수 없다고 하면: **완료**를 클릭하고, **시스템 설정 → 개인정보 보호 및 보안**에서
**그래도 열기**를 클릭하세요. 표시 언어는 **설정** 위쪽에서 한국어를 고를 수 있습니다.
[한국어 설명](https://github.com/LuckyLetter/penwise/blob/main/docs/readme/ko.md)

</details>

---

**Files:** **Penwise.dmg** is the app. The `.whl` file is the same version of Penwise for its own updates (and for
`pip`); you don't need to download it.
