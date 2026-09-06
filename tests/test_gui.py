"""Интеграционные тесты на настоящем Tk.

Пропускаются там, где нет tkinter или дисплея. Запуск с виртуальным экраном:

    xvfb-run -a pytest tests/test_gui.py
"""

import time

import pytest

tk = pytest.importorskip("tkinter", reason="tkinter недоступен")

from dp_typing import theme  # noqa: E402
from dp_typing.words import Mode  # noqa: E402


@pytest.fixture
def app(tmp_path, monkeypatch):
    """Живое окно. Профиль уводим во временный каталог, чтобы не трогать личный."""
    from dp_typing import app as app_module
    from dp_typing import storage

    monkeypatch.setattr(storage, "config_path", lambda: tmp_path / "profile.json")
    monkeypatch.setattr(app_module, "save_profile",
                        lambda *a, **k: storage.save(*a, path=tmp_path / "profile.json", **k))
    try:
        window = app_module.TypingApp()
    except tk.TclError as exc:                      # нет дисплея
        pytest.skip(f"дисплей недоступен: {exc}")
    settle(window)
    yield window
    window.destroy()


def settle(window, ms: int = 400) -> None:
    """Прокрутить цикл событий, дав сработать отложенным задачам."""
    deadline = time.time() + ms / 1000
    while time.time() < deadline:
        window.update()
        time.sleep(0.005)


def press(window, ch: str, keysym: str = "a") -> None:
    window._on_key(type("Event", (), {"char": ch, "keysym": keysym, "state": 0})())
    window.update()


def pending_after_jobs(window) -> int:
    return len(window.tk.splitlist(window.tk.call("after", "info")))


# ------------------------------------------------------------------- разметка

def test_all_sections_are_visible(app):
    """Ловушка Tk: Text просит 24 строки и вытесняет всё, что ниже."""
    for widget in (app.text, app.combo_canvas, app.kb_holder):
        assert widget.winfo_ismapped(), f"{widget} не отображается"
        assert widget.winfo_height() > 10


def test_keyboard_hint_is_drawn_and_follows_the_caret(app):
    assert len(app._kb_items) > 25
    assert " " in app._kb_items

    target = app.session.target
    assert app._hot_key == target[0].lower()
    rect, _ = app._kb_items[app._hot_key]
    assert app.kb_canvas.itemcget(rect, "fill") == theme.KEY_NEXT_BG
    assert app.finger_var.get()

    press(app, target[0])
    assert app._hot_key == target[1].lower()


# ---------------------------------------------------------------- ввод

def test_typing_tags_characters(app):
    target = app.session.target
    press(app, target[0])
    assert "ok" in app.text.tag_names("1.0")
    assert "caret" in app.text.tag_names("1.1")

    press(app, "№")
    assert "bad" in app.text.tag_names("1.1")
    assert app.session.combo == 0


def test_stats_reach_the_screen(app):
    for ch in app.session.target[:6]:
        press(app, ch)
    settle(app, 300)
    assert app.stat_vars["err"].get() == "0"
    assert app.stat_vars["acc"].get() == "100%"
    assert int(app.stat_vars["cpm"].get()) <= 1500


# --------------------------------------------------- таймеры и нагрузка на CPU

def test_no_pending_jobs_while_idle(app):
    """В покое приложение не должно будить процессор вообще."""
    settle(app, 300)
    assert pending_after_jobs(app) == 0


def test_exactly_one_ticker_during_a_test(app):
    press(app, app.session.target[0])
    assert app._tick_id is not None
    assert pending_after_jobs(app) <= 2       # тикер + возможный кадр анимации


def test_finish_schedules_exactly_one_transition(app):
    for ch in app.session.target:
        press(app, ch)
    assert app.session.finished
    assert app._tick_id is None
    assert app._next_id is not None

    # Ревью #2: повторный финиш не имеет права поставить второй таймер.
    press(app, "x")                            # досрочный переход
    assert app._next_id is None
    assert app.session.pos == 0


def test_idle_again_after_a_full_cycle(app):
    """Отработав фразу и перейдя к следующей, приложение снова засыпает."""
    from dp_typing.app import NEXT_TEST_MS

    for ch in app.session.target:
        press(app, ch)
    settle(app, NEXT_TEST_MS + 400)            # ждём автопереход
    assert app._next_id is None
    assert pending_after_jobs(app) == 0


# ------------------------------------------------------------------ команды

def test_language_switch_redraws_the_keyboard(app):
    start = app.lang
    app.toggle_language()
    settle(app)
    assert app.lang != start
    expected = "q" if app.lang == "en" else "й"
    assert expected in app._kb_items


def test_mode_cycle_visits_every_mode(app):
    seen = {app.mode}
    for _ in range(len(Mode)):
        app.cycle_mode()
        seen.add(app.mode)
    assert seen == set(Mode)


def test_help_overlay_toggles(app):
    app.toggle_help()
    app.update()
    assert app.help_frame.winfo_ismapped()
    app.toggle_help()
    app.update()
    assert not app.help_frame.winfo_ismapped()


def test_keyboard_can_be_hidden(app):
    app.toggle_keyboard()
    app.update()
    assert not app.kb_holder.winfo_ismapped()
    app.toggle_keyboard()
    settle(app)
    assert app.kb_holder.winfo_ismapped()


def test_restart_keeps_the_same_phrase(app):
    phrase = app.session.target
    press(app, phrase[0])
    app.restart_test()
    assert app.session.target == phrase
    assert app.session.pos == 0
    assert app.session.keystrokes == 0


# --------------------------------------------------- высота поля с фразой

@pytest.mark.parametrize("phrase", [
    "коротко",
    "фраза подлиннее которая наверняка не влезет в одну строку и перенесётся",
    "совсем длинный текст который обязан занять несколько строк подряд потому что "
    "слов в нём очень много и они идут одно за другим без остановки и так далее",
])
def test_phrase_is_never_clipped(app, phrase):
    """Поле подгоняет высоту под перенос — последний символ обязан быть виден."""
    from dp_typing.engine import TypingSession

    app.session = TypingSession(phrase)
    app._render_target(phrase)
    app.update_idletasks()
    assert app.text.dlineinfo("end-2c") is not None, "текст обрезан по высоте"


def test_short_phrase_does_not_reserve_extra_rows(app):
    from dp_typing.engine import TypingSession

    app.session = TypingSession("коротко")
    app._render_target("коротко")
    app.update_idletasks()
    assert int(app.text.cget("height")) == 1
