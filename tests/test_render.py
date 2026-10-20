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


def test_risky_changes_are_listed_but_not_applied():
    out = render.pretty(check("As shown in [12], it works.", "As shown, it works."), color=False)
    assert "As shown in [12], it works." in out
    assert "Not applied: it would remove a citation" in out
