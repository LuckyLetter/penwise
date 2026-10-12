from penwise import engine, render


def check(original, edited):
    return engine.check(original, lambda system, messages: edited, model="m")


def test_replacements_get_an_arrow_in_color():
    out = render.pretty(check("They achieve it.", "They achieved it."), color=True)
    assert "achieve" + render.RESET + render.DIM + "→" in out


def test_plain_output_marks_changes_with_brackets():
    out = render.pretty(check("They achieve it.", "They achieved it."), color=False)
    assert "They [-achieve-]{+achieved+} it." in out
    assert "Word form" in out


def test_no_changes():
    assert "your text looks good" in render.pretty(check("Fine.", "Fine."), color=False)
