import pytest

from penwise import presets, prompts


@pytest.mark.parametrize(
    "app, title, style",
    [
        ("com.apple.mail", "", "email"),
        ("com.microsoft.Outlook", "Inbox", "email"),
        ("com.tinyspeck.slackmacgap", "", "chat"),
        ("com.google.Chrome", "Inbox (3) - me@uni.edu - Gmail", "email"),
        ("com.apple.Safari", "general | Slack", "chat"),
        ("com.google.Chrome", "Overleaf, Online LaTeX Editor", "academic"),
        ("com.microsoft.Word", "Slack notes.docx", "academic"),  # titles only count in browsers
        ("com.alibaba.DingTalkMac", "", "chat"),
        ("com.electron.lark", "", "chat"),  # Feishu / Lark
        ("com.tencent.WeWorkMac", "", "chat"),  # WeCom
        ("com.google.Chrome", "QQ邮箱 - 收件箱", "email"),
        ("com.apple.Safari", "网易邮箱6.0版", "email"),
        ("com.google.Chrome", "飞书 - 消息", "chat"),
        ("", "", "academic"),
    ],
)
def test_style_for(app, title, style):
    assert presets.style_for(app, title) == style


def test_the_tone_hint_is_only_for_improve():
    system, _ = prompts.edit_messages("Hi, can you check?", "improve", style="email")
    assert "The text is an email" in system
    system, _ = prompts.edit_messages("Hi, can you check?", "fix", style="email")
    assert "The text is an email" not in system
    system, _ = prompts.edit_messages("Hi, can you check?", "improve", style="academic")
    assert system == prompts.SYSTEM["improve"]


def test_reasoning_effort_for_suggested_models():
    assert presets.reasoning_effort_for("openai/gpt-6-luna") == "none"
    assert presets.reasoning_effort_for("someone/unknown-model") == ""
