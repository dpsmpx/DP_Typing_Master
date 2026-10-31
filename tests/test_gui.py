"""Интеграционные тесты на настоящем Tk.

Пропускаются там, где нет tkinter или дисплея. Запуск с виртуальным экраном:

    xvfb-run -a pytest tests/test_gui.py

С переменной ``DP_REQUIRE_GUI=1`` (так запускает CI) отсутствие tkinter или
дисплея — ошибка, а не пропуск: иначе сломанный интерфейс прятался бы за
зелёной галочкой из одних «skipped».
"""

import os
import time

import pytest

REQUIRE_GUI = bool(os.environ.get("DP_REQUIRE_GUI"))
if REQUIRE_GUI:
    import tkinter as tk
else:
    tk = pytest.importorskip("tkinter", reason="tkinter недоступен")

from dp_typing import theme  # noqa: E402
from dp_typing.words import Mode  # noqa: E402


def _make_window(app_module):
    try:
        return app_module.TypingApp()
    except tk.TclError as exc:                      # нет дисплея
        if REQUIRE_GUI:
            raise
        pytest.skip(f"дисплей недоступен: {exc}")


@pytest.fixture
def app(tmp_path, monkeypatch):
    """Живое окно. Профиль уводим во временный каталог, чтобы не трогать личный."""
    from dp_typing import app as app_module
    from dp_typing import storage

    monkeypatch.setattr(storage, "config_path", lambda: tmp_path / "profile.json")
    monkeypatch.setattr(app_module, "save_profile",
                        lambda *a, **k: storage.save(*a, path=tmp_path / "profile.json", **k))
    window = _make_window(app_module)
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


def visible_background(window, index: str) -> str:
    """Фон, который Tk нарисует под символом: у тега с наивысшим приоритетом
    среди задающих фон (tag_names отдаёт теги по возрастанию приоритета)."""
    for tag in reversed(window.text.tag_names(index)):
        bg = window.text.tag_cget(tag, "background")
        if bg:
            return bg
    return window.text.cget("background")


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


def test_result_stays_until_a_key_is_pressed(app):
    """Итог фразы не исчезает сам: его можно спокойно прочитать (A-13)."""
    phrase = app.session.target
    for ch in phrase:
        press(app, ch)
    assert app.session.finished
    assert app._tick_id is None
    settle(app, 1800)                          # раньше тут был автопереход
    assert app.session.finished and app.session.target == phrase
    assert app.result_var.get()
    assert "любая клавиша" in app.hint_var.get()

    press(app, "x")                            # любая клавиша — следующая фраза
    assert not app.session.finished
    assert app.session.pos == 0 and app.session.keystrokes == 0
    assert app.result_var.get() == ""


def test_idle_again_after_a_full_cycle(app):
    """Отработав фразу, приложение засыпает — даже таймера перехода нет."""
    for ch in app.session.target:
        press(app, ch)
    settle(app, 500)                           # кадры анимации комбо доиграют
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


def test_keyboard_toggle_keeps_its_place(app):
    """F6 дважды не должен переносить клавиатуру под строку подсказок."""
    order = app.body.pack_slaves()
    app.toggle_keyboard()
    app.toggle_keyboard()
    settle(app)
    assert app.body.pack_slaves() == order
    slaves = app.body.pack_slaves()
    assert slaves.index(app.kb_holder) < slaves.index(app.footer_label)
    assert app.kb_holder.winfo_y() < app.footer_label.winfo_y()


# ---------------------------------------------------------- строгий режим

def test_strict_error_is_visible_under_caret(app):
    """Строгий режим держит курсор на ошибке — она обязана быть видна."""
    app.toggle_strict()
    target = app.session.target
    press(app, target[0])
    wrong = "№"
    press(app, wrong)
    assert app.session.pos == 1
    tags = app.text.tag_names("1.1")
    assert "caret_bad" in tags and "caret" not in tags
    assert visible_background(app, "1.1") == theme.CARET_BAD

    press(app, target[1])                     # исправились — каретка обычная
    assert "caret" in app.text.tag_names("1.2")
    assert "caret_bad" not in app.text.tag_names("1.1")
    assert "ok" in app.text.tag_names("1.1")


def test_strict_backspace_clears_error_caret(app):
    app.toggle_strict()
    press(app, "№")
    assert "caret_bad" in app.text.tag_names("1.0")
    app._on_key(type("Event", (), {"char": "\b", "keysym": "BackSpace", "state": 0})())
    app.update()
    tags = app.text.tag_names("1.0")
    assert "caret" in tags and "caret_bad" not in tags


# --------------------------------------------------------- маленькое окно

LONG_PHRASE = (
    "совершенно длинная фраза которая обязательно переносится минимум "
    "на три строки при самом узком допустимом окне тренажёра"
)


#: Худший случай: девять слов предельной длины (MAX_WORD_LEN = 12).
WORST_PHRASE = " ".join(["переносилось"] * 9)


def _assert_everything_fits(app):
    for widget in (app.text, app.combo_canvas, app.kb_holder, app.footer_label):
        assert widget.winfo_ismapped(), f"{widget} не отображается"
    # Ни одна секция не ужата pack-ом меньше, чем просит: иначе её низ срезан.
    for widget in (*app.body.pack_slaves(), *app.kb_holder.pack_slaves()):
        assert widget.winfo_height() >= widget.winfo_reqheight(), f"{widget} срезан"
    bottom = app.footer_label.winfo_y() + app.footer_label.winfo_height()
    assert bottom <= app.body.winfo_height(), "подсказки срезаны снизу"
    # Клавиатура целиком внутри своего холста: все четыре ряда и пробел.
    assert app._kb_items, "клавиатура не нарисована"
    _, y0, _, y1 = app.kb_canvas.bbox("all")
    assert y0 >= 0 and y1 <= app.kb_canvas.winfo_height() + 1
    assert app.text.dlineinfo("end-2c") is not None, "фраза обрезана"


def _render(app, phrase):
    """Начать тест с заданной фразой тем же путём, что и new_test."""
    app._start_session(phrase)
    settle(app, 400)


@pytest.mark.parametrize("phrase", [LONG_PHRASE, WORST_PHRASE])
def test_minimum_window_fits_everything(app, phrase):
    w, h = (int(v) for v in app.wm_minsize())
    app.geometry(f"{w}x{h}")
    settle(app, 600)
    _render(app, phrase)
    assert app.compact
    _assert_everything_fits(app)


def test_long_phrase_fits_default_window(app):
    _render(app, WORST_PHRASE)
    _assert_everything_fits(app)


def test_density_returns_to_normal_when_window_grows(app):
    app.geometry("760x560")
    settle(app, 600)
    _render(app, "коротко")
    assert app.compact
    app.geometry("1040x720")
    settle(app, 600)
    assert not app.compact
    _assert_everything_fits(app)


def test_default_window_uses_normal_density(app):
    _render(app, "коротко и ясно")
    assert not app.compact


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


# ================================================================ этап 2.1

def press_key(window, ch: str, state: int = 0) -> None:
    window._on_key(type("Event", (), {"char": ch, "keysym": "a", "state": state})())
    window.update()


def notice_text(window) -> str:
    window.update()
    return window.notice.cget("text") if window.notice.winfo_ismapped() else ""


# ------------------------------------------------- раскладка ОС и Caps Lock

def test_wrong_system_layout_is_reported_and_counted(app):
    """A-10: латиница в русской тренировке — подсказка, но ошибка засчитана."""
    assert app.lang == "ru"
    press_key(app, "g")
    assert "раскладк" in notice_text(app) and "русскую" in notice_text(app)
    assert app.session.errors == 1               # выбор: предупреждать и считать
    press_key(app, app.session.target[app.session.pos])
    assert notice_text(app) == ""                # исправились — плашка ушла


def test_caps_lock_is_reported(app):
    """A-11: по биту Caps Lock и по заглавной вместо строчной."""
    press_key(app, app.session.target[0].upper())
    assert "Caps Lock" in notice_text(app)
    app.new_test()
    assert notice_text(app) == ""                # новая фраза — чистый лист
    press_key(app, "ы" if app.session.target[0] != "ы" else "ф", state=0x2)
    assert "Caps Lock" in notice_text(app)


def test_input_notice_disappears_by_itself(app, monkeypatch):
    from dp_typing import app as app_module

    monkeypatch.setattr(app_module, "INPUT_NOTICE_MS", 150)
    press_key(app, "g")
    assert notice_text(app)
    settle(app, 400)
    assert notice_text(app) == ""
    assert app._notice_id is None


# -------------------------------------------------- сброс с подтверждением

def test_reset_needs_a_second_press(app):
    """A-12: одно F7 не стирает статистику, второе подряд — стирает."""
    app.profile.tests = 7
    app.request_reset()
    assert app.profile.tests == 7
    assert "F7" in notice_text(app)
    app.request_reset()
    assert app.profile.tests == 0
    assert "сброшена" in notice_text(app)


def test_notice_does_not_cover_the_result(app, monkeypatch):
    """Плашка и итог фразы не рисуются друг поверх друга."""
    from dp_typing import app as app_module

    monkeypatch.setattr(app_module, "RESET_CONFIRM_MS", 150)
    for ch in app.session.target:
        press(app, ch)
    result = app.result_var.get()
    assert result
    app.request_reset()
    assert notice_text(app) and app.result_var.get() == ""
    settle(app, 400)                             # плашка ушла — итог вернулся
    assert notice_text(app) == ""
    assert app.result_var.get() == result


def test_reset_confirmation_expires(app):
    app.profile.tests = 7
    app.request_reset()
    app._reset_armed_until = 0.0                 # прошло больше 3 секунд
    app.request_reset()
    assert app.profile.tests == 7                # это снова первое нажатие


# --------------------------------------------------------- модальная справка

def test_help_blocks_typing_and_esc_closes_it(app):
    """A-06: при открытой справке печать не уходит в тест, Esc её закрывает."""
    phrase = app.session.target
    app.toggle_help()
    press(app, phrase[0])
    assert app.session.keystrokes == 0
    assert app._tick_id is None
    app.event_generate("<Escape>")
    app.update()
    assert not app.help_frame.winfo_ismapped()
    assert app.session.target == phrase          # Esc не пропустил фразу


# -------------------------------------------------- брошенная фраза и пауза

def test_skipped_phrase_feeds_key_statistics(app):
    """A-08: Esc не засчитывает тест, но ошибки идут в слабые клавиши."""
    for _ in range(3):
        press(app, "№")
    app.event_generate("<Escape>")
    app.update()
    assert app.profile.tests == 0
    assert sum(app.profile.char_errors.values()) == 3


def test_timer_sleeps_while_idle(app, monkeypatch):
    """A-07: после простоя таймер засыпает и показывает паузу."""
    from dp_typing import engine

    monkeypatch.setattr(engine, "IDLE_GAP", 0.1)
    target = app.session.target
    press(app, target[0])
    settle(app, 500)
    assert app._tick_id is None
    assert pending_after_jobs(app) == 0
    assert "пауза" in app.result_var.get()

    press(app, target[1])                        # вернулись — время пошло
    assert app._tick_id is not None
    assert app.result_var.get() == ""


# --------------------------------------------------------------------- ё

def test_yo_has_a_key_and_accepts_e(app):
    """A-09: у «ё» есть клавиша и подсказка, «е» на её месте — не ошибка."""
    _render(app, "ёж ещё")
    assert app._hot_key == "ё"
    rect, _ = app._kb_items["ё"]
    assert app.kb_canvas.itemcget(rect, "fill") == theme.KEY_NEXT_BG
    assert "мизинец" in app.finger_var.get() and "«е»" in app.finger_var.get()
    for ch in "еж еще":
        press(app, ch)
    assert app.session.finished
    assert app.session.errors == 0


# ------------------------------------------------------- ступени и чипы

def test_stage_chip_only_in_lessons(app):
    """A-18: вне уроков чипа ступени нет — кликнуть по нему нельзя."""
    app.mode = Mode.COMMON
    app._refresh_chips()
    app.update()
    assert not app._chips[2].winfo_ismapped()
    app.mode = Mode.LESSON
    app._refresh_chips()
    app.update()
    assert app._chips[2].winfo_ismapped()


def test_f4_enters_lessons_and_does_not_wrap(app):
    """A-15: F4 с последней ступени не прыгает на первую."""
    from dp_typing.words import lesson_stages

    last = len(lesson_stages(app.lang)) - 1
    app.mode, app.stage = Mode.COMMON, last
    app.next_stage()
    assert app.mode is Mode.LESSON and app.stage == last    # просто вошли в уроки
    app.next_stage()
    assert app.stage == last
    assert "последняя" in notice_text(app)
    app.stage = 0
    app.prev_stage()
    assert app.stage == 0
    assert "первая" in notice_text(app)


# ----------------------------------------------------------- мелкие правки

def test_stat_tiles_have_equal_width(app):
    """A-20: ширина плитки не зависит от длины подписи."""
    shown = [tile for tile in app.stat_tiles if tile.winfo_ismapped()]
    widths = {tile.winfo_width() for tile in shown}
    assert max(widths) - min(widths) <= 1
    right = shown[-1].winfo_x() + shown[-1].winfo_width()
    assert abs(right - app._text_wrap.winfo_width()) <= 1     # край вровень с фразой


def test_accuracy_colour_matches_what_is_shown():
    """A-19: «97%» всегда одного цвета, сколько бы ни было после запятой."""
    assert theme.accuracy_color(96.7) == theme.accuracy_color(97.0) == theme.GOOD
    assert theme.accuracy_color(96.4) == theme.WARN


def wrapping_phrase(app, lines: int = 2) -> str:
    """Фраза, которая при текущем шрифте займёт не меньше ``lines`` строк.

    Длина подбирается по реальной ширине шрифта: в сборках Tk без Xft
    символы втрое уже, и «длинная» фраза влезала бы в одну строку.
    """
    width = app.text.winfo_width() - 2 * int(app.text.cget("padx"))
    words = ["фраза", "подлиннее", "которая", "наверняка", "перенесётся", "на",
             "следующую", "строку"]
    out: list[str] = []
    while app.f_target.measure(" ".join(out)) < width * (lines - 0.5):
        out.append(words[len(out) % len(words)])
    return " ".join(out)


def test_phrase_panel_top_does_not_jump(app):
    """A-21: панель с фразой не прыгает, когда меняется число строк."""
    _render(app, "коротко")
    top = app._text_wrap.winfo_y()
    _render(app, wrapping_phrase(app))
    assert int(app.text.cget("height")) >= 2
    assert app._text_wrap.winfo_y() == top


def test_lines_are_centred_without_tk_justify(app):
    """A-05: строки центрируются отступом, а не justify=center.

    При justify=center Tk растягивал фон первого символа строки до левого
    края — каретка в начале строки превращалась в полосу.
    """
    phrase = wrapping_phrase(app)
    _render(app, phrase)
    assert len(app._lines) >= 2
    text = app.text
    assert text.tag_cget("base", "justify") in ("", "left")
    padx = int(text.cget("padx"))
    width = text.winfo_width() - 2 * padx
    for row, line in enumerate(app._lines, start=1):
        x, _, _, _ = text.bbox(f"{row}.0")
        left = x - padx
        right = width - left - app.f_target.measure(line.rstrip(" "))
        assert abs(left - right) <= app.f_target.measure("0") + 1, f"строка {row} не по центру"

    # Отступ залит цветом панели, а не фоном первого символа строки.
    for row in range(1, len(app._lines) + 1):
        assert text.tag_cget(f"line{row}", "lmargincolor") == theme.PANEL

    # Каретка в начале второй строки — ровно на своём символе.
    start_of_second = len(app._lines[0])
    for ch in phrase[:start_of_second]:
        press(app, ch)
    assert app._spans[app.session.pos][0] == "2.0"
    assert "caret" in text.tag_names("2.0")


def test_marks_survive_a_resize(app):
    """Перенос строк пересчитывается при ресайзе, разметка не теряется."""
    target = app.session.target
    press(app, target[0])
    press(app, "№")
    app.geometry("800x600")
    settle(app, 600)
    assert "ok" in app.text.tag_names(app._spans[0][0])
    assert "bad" in app.text.tag_names(app._spans[1][0])
    assert app._caret_tag in app.text.tag_names(app._spans[2][0])


# ------------------------------------------------------------------ HiDPI

@pytest.fixture
def hidpi_app(tmp_path, monkeypatch):
    """Окно на экране 192 dpi (масштаб 200%)."""
    from dp_typing import app as app_module
    from dp_typing import storage

    original = {}

    def double(self):
        original["scaling"] = self.tk.call("tk", "scaling")
        self.tk.call("tk", "scaling", 2 * 96 / 72)
        return 2.0

    monkeypatch.setattr(storage, "config_path", lambda: tmp_path / "profile.json")
    monkeypatch.setattr(app_module, "save_profile",
                        lambda *a, **k: storage.save(*a, path=tmp_path / "profile.json", **k))
    monkeypatch.setattr(app_module.TypingApp, "_detect_scale", double)
    window = _make_window(app_module)
    window.geometry("2080x1440")
    settle(window, 800)
    yield window
    # tk scaling общий на весь дисплей процесса — без возврата следующие
    # окна в этом же прогоне тестов тоже считали бы экран HiDPI.
    window.tk.call("tk", "scaling", original["scaling"])
    window.destroy()


def test_hidpi_layout_scales(hidpi_app):
    """A-04: при масштабе 200% ничего не налезает друг на друга."""
    app = hidpi_app
    assert app.scale == 2.0
    _render(app, "обычная фраза для проверки масштаба")
    _assert_everything_fits(app)

    # Рамка текста включает запас под нижние выносные элементы, которых у
    # «×N» нет, поэтому перекрытие рамок в пределах этого запаса — норма.
    c = app.combo_canvas
    value, caption = c.bbox(app._combo_value), c.bbox(app._combo_caption)
    descent = app.f_combo.metrics("descent")
    assert value[3] - descent <= caption[1], "«×N» налезает на «КОМБО»"

    for ch, (rect, label) in app._kb_items.items():
        r, t = app.kb_canvas.bbox(rect), app.kb_canvas.bbox(label)
        assert t[0] >= r[0] - 1 and t[2] <= r[2] + 1, f"буква «{ch}» шире клавиши"
        assert t[1] >= r[1] - 1 and t[3] <= r[3] + 1, f"буква «{ch}» выше клавиши"

    header = app._header_bar
    assert header.winfo_reqwidth() <= header.winfo_width(), "заголовок обрезан"


# ================================================================ этап 2.2

def test_record_tile_follows_language_and_mode(app):
    """A-14: рекорд в уроках не показывается как рекорд обычного текста."""
    app.profile.records.update({"ru/lesson/phrase": 90.0, "ru/common/phrase": 40.0})
    app.mode = Mode.COMMON
    app._refresh_chips()
    app.new_test()
    assert app.stat_vars["best"].get() == "40"
    app.mode = Mode.LESSON
    app._refresh_chips()
    app.new_test()
    assert app.stat_vars["best"].get() == "90"
    app.toggle_language()
    assert app.stat_vars["best"].get() == "0"


def test_new_record_is_announced(app):
    app.profile.records[app._record_key()] = 0.5          # заведомо побьём
    for ch in app.session.target:
        press(app, ch)
    assert "новый рекорд" in app.result_var.get()


# ------------------------------------------- заглавные, знаки, цифры (A-27)

def test_text_options_change_the_text(app):
    app.mode = Mode.COMMON
    app._refresh_chips()
    app.toggle_caps()
    app.toggle_punct()
    target = app.session.target
    assert target[0].isupper()
    assert target[-1] in ".!?"
    on = app._option_chips["caps"].cget("fg")
    assert on == theme.ACCENT
    app.toggle_caps()
    assert app._option_chips["caps"].cget("fg") != theme.ACCENT


def test_full_keyboard_has_number_row_and_shifts(app):
    app.mode = Mode.COMMON
    app._refresh_chips()
    basic = set(app._kb_items)
    assert "1" not in basic and "shift_left" not in basic
    app.toggle_digits()
    settle(app)
    full = set(app._kb_items)
    assert {"1", "0", "shift_left", "shift_right", "ё"} <= full
    assert int(app.kb_canvas.cget("height")) > 0
    # В уроках опций нет — и клавиатура снова простая.
    app.mode = Mode.LESSON
    app._refresh_chips()
    settle(app)
    assert "shift_left" not in app._kb_items
    assert not app._option_box.winfo_ismapped()


def test_capital_highlights_key_and_opposite_shift(app):
    app.mode = Mode.COMMON
    app._refresh_chips()
    app.toggle_caps()
    settle(app)
    _render(app, "Привет мир")
    assert app._hot_key == "п" and app._hot_shift == "shift_right"   # п — левая рука
    rect, _ = app._kb_items["shift_right"]
    assert app.kb_canvas.itemcget(rect, "fill") == theme.KEY_NEXT_BG
    assert "Shift правой" in app.finger_var.get()
    press_key(app, "П", state=0x1)                   # Shift зажат — это не Caps Lock
    assert notice_text(app) == ""
    assert app.session.errors == 0
    assert app._hot_shift is None                    # «р» — без Shift


def test_punctuation_hint_on_russian_layout(app):
    app.mode = Mode.COMMON
    app._refresh_chips()
    app.toggle_punct()
    settle(app)
    _render(app, "да, нет")
    for ch in "да":
        press(app, ch)
    assert app._hot_key == "." and app._hot_shift == "shift_left"   # запятая — Shift+точка
    assert "правый мизинец" in app.finger_var.get()


def test_record_key_includes_text_options(app):
    app.mode = Mode.COMMON
    app._refresh_chips()
    plain = app._record_key()
    app.toggle_punct()
    assert app._record_key() != plain
    assert app._record_key().endswith("/.")


def test_options_are_persisted(app, tmp_path):
    import json

    app.mode = Mode.COMMON
    app._refresh_chips()
    app.toggle_digits()
    app._persist()
    saved = json.loads((tmp_path / "profile.json").read_text(encoding="utf-8"))
    assert saved["digits"] is True and saved["caps"] is False


def test_full_keyboard_fits_minimum_window(app):
    app.mode = Mode.COMMON
    app._refresh_chips()
    app.toggle_caps()
    app.toggle_punct()
    app.toggle_digits()
    w, h = (int(v) for v in app.wm_minsize())
    app.geometry(f"{w}x{h}")
    settle(app, 600)
    _render(app, WORST_PHRASE)
    _assert_everything_fits(app)
    for ch, (rect, label) in app._kb_items.items():
        r, t = app.kb_canvas.bbox(rect), app.kb_canvas.bbox(label)
        assert t[1] >= r[1] - 1 and t[3] <= r[3] + 1, f"подпись «{ch}» выше клавиши"


# ------------------------------------------------------------ длина теста

def test_phrase_has_no_extra_tile(app):
    from dp_typing.words import LENGTHS

    app.set_length(LENGTHS[0])
    app.update()
    assert not app.stat_tiles[-1].winfo_ismapped()


def test_word_count_test_counts_words(app):
    from dp_typing.words import Length

    app.mode = Mode.COMMON
    app._refresh_chips()
    app.set_length(Length("words", 25))
    settle(app, 300)
    target = app.session.target
    assert len(target.split()) == 25
    assert app.stat_tiles[-1].winfo_ismapped()
    assert app._extra_caption.cget("text") == "СЛОВА"
    assert app.stat_vars["extra"].get() == "0/25"
    first_two = target[: target.index(" ", target.index(" ") + 1) + 1]
    for ch in first_two:
        press(app, ch)
    app._refresh_stats(force=True)
    assert app.stat_vars["extra"].get() == "2/25"
    assert "25 СЛОВ" in app.length_var.get()


def test_long_text_scrolls_three_lines_at_a_time(app):
    from dp_typing.words import Length

    app.set_length(Length("words", 100))
    settle(app, 300)
    assert len(app._lines) > 3
    assert int(app.text.cget("height")) == 3
    for ch in app.session.target[: len(app._lines[0]) + len(app._lines[1])]:
        press(app, ch)
    # Каретка на третьей строке — сверху вторая, только что набранная.
    assert app._rows[app.session.pos] == 3
    assert app._view_top == 2
    assert app.text.index("@0,0").startswith("2.")


def test_timed_test_counts_down_and_finishes_by_itself(app):
    from dp_typing.words import Length

    app.set_length(Length("time", 15))
    settle(app, 200)
    assert app.session.time_limit == 15
    assert app._extra_caption.cget("text") == "ОСТАЛОСЬ, С"
    assert app.stat_vars["extra"].get() == "15"
    app.session.time_limit = 0.3                 # не ждать 15 секунд в тесте
    press(app, app.session.target[0])
    settle(app, 800)
    assert app.session.finished and app.session.timed_out
    assert app.result_var.get()
    assert app.stat_vars["extra"].get() == "0"
    assert pending_after_jobs(app) == 0
    assert app.profile.tests == 1


def test_length_is_part_of_the_record_and_persisted(app, tmp_path):
    import json

    from dp_typing.words import Length

    app.mode = Mode.COMMON
    app._refresh_chips()
    phrase_key = app._record_key()
    app.set_length(Length("time", 60))
    assert app._record_key() != phrase_key and "/t60" in app._record_key()
    app._persist()
    saved = json.loads((tmp_path / "profile.json").read_text(encoding="utf-8"))
    assert saved["length"] == "t60"


def test_f8_cycles_lengths(app):
    from dp_typing.words import LENGTHS

    app.set_length(LENGTHS[0])
    app.cycle_length()
    assert app.length == LENGTHS[1]
    app.cycle_length(-1)
    app.cycle_length(-1)
    assert app.length == LENGTHS[-1]
