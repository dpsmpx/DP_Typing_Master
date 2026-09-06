"""Тесты ядра. Каждый блок закрывает конкретный пункт ревью."""

import pytest

from dp_typing.engine import (
    CHARS_PER_WORD,
    MAX_CPM,
    Mark,
    Profile,
    TypingSession,
)


class FakeClock:
    """Управляемые часы — метрики становятся детерминированными."""

    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def play(target, typed, *, strict=False, clock=None, elapsed=None):
    """Прогнать строку `typed` по сессии с целью `target`."""
    clock = clock or FakeClock()
    s = TypingSession(target, strict=strict, clock=clock)
    for ch in typed:
        if ch == "\b":
            s.backspace()
        else:
            s.type_char(ch)
        if elapsed is not None:
            clock.advance(elapsed)
    return s


# --------------------------------------------------- ревью #1: ошибки считаются

def test_errors_are_counted_even_when_corrected():
    """Опечатка, исправленная бэкспейсом, обязана остаться в статистике."""
    s = play("кот", "кит\b\bот")
    assert s.finished
    assert s.errors == 1
    assert s.metrics().accuracy < 100.0


def test_perfect_run_is_100_percent():
    s = play("кот", "кот")
    assert s.errors == 0
    assert s.metrics().accuracy == 100.0


def test_accuracy_uses_keystrokes_not_final_text():
    """Итоговый текст верный, но одно нажатие было ошибочным — это видно."""
    s = play("aaaa", "ab\baaa")
    assert s.finished
    assert s.keystrokes == 5        # a b a a a; бэкспейс нажатием не считается
    assert s.errors == 1
    assert s.correct_chars == 4     # финальный текст безупречен...
    assert s.metrics().accuracy == pytest.approx(80.0)   # ...а точность нет


# ------------------------------------------- ревью #4: перебор не даёт 100%

def test_wrong_char_at_every_position_is_zero_accuracy():
    s = play("abc", "xyz")
    assert s.finished
    assert s.errors == 3
    assert s.metrics().accuracy == 0.0
    assert s.metrics().correct_chars == 0


def test_cannot_type_past_the_end():
    s = play("ab", "ab")
    assert s.finished
    assert s.type_char("c").accepted is False
    assert s.keystrokes == 2


# ------------------------------------------ ревью #5: CPM не улетает в космос

def test_cpm_is_bounded_for_instant_input():
    """Вставка из буфера не должна рисовать десятки тысяч знаков в минуту."""
    clock = FakeClock()
    s = TypingSession("abcdefghij", clock=clock)
    for ch in "abcdefghij":
        s.type_char(ch)          # время не двигаем — «мгновенный» ввод
    m = s.metrics()
    assert m.cpm == MAX_CPM
    assert m.raw_wpm == MAX_CPM / CHARS_PER_WORD


def test_realistic_speed_is_not_clamped():
    clock = FakeClock()
    s = TypingSession("abcde", clock=clock)
    for ch in "abcde":
        clock.advance(0.2)       # 300 знаков/мин — быстро, но по-человечески
        s.type_char(ch)
    assert s.metrics().cpm < MAX_CPM


def test_cpm_matches_hand_calculation():
    clock = FakeClock()
    s = TypingSession("abcde", clock=clock)
    for ch in "abcde":
        clock.advance(1.0)
        s.type_char(ch)
    # Отсчёт идёт от первого нажатия до последнего: 5 символов, 4 секунды.
    assert s.elapsed() == pytest.approx(4.0)
    m = s.metrics()
    assert m.cpm == pytest.approx(75.0)
    assert m.wpm == pytest.approx(75.0 / CHARS_PER_WORD)


def test_timer_starts_on_first_char_not_on_construction():
    clock = FakeClock()
    s = TypingSession("ab", clock=clock)
    clock.advance(100.0)         # пользователь думал 100 секунд
    s.type_char("a")
    clock.advance(1.0)
    s.type_char("b")
    assert s.elapsed() == pytest.approx(1.0)


# ------------------------------------------------------------------- комбо

def test_combo_grows_and_breaks():
    s = play("abcdef", "abcXef")
    assert s.best_combo == 3
    assert s.combo == 2


def test_combo_cannot_be_farmed_by_retyping():
    """Набрал — стёр — набрал не должно накручивать комбо."""
    straight = play("abcd", "abcd")
    farmed = play("abcd", "abc\bc\bc\bcd")
    assert farmed.best_combo <= straight.best_combo


def test_backspace_over_correct_char_lowers_combo():
    s = play("abcd", "abc")
    assert s.combo == 3
    s.backspace()
    assert s.combo == 2


def test_effect_reports_combo_transitions():
    s = TypingSession("ab", clock=FakeClock())
    assert s.type_char("a").combo_gained is True
    eff = s.type_char("X")
    assert eff.combo_broken is True and eff.correct is False


# -------------------------------------------------------------- строгий режим

def test_strict_mode_blocks_advance_on_error():
    s = TypingSession("ab", strict=True, clock=FakeClock())
    s.type_char("X")
    assert s.pos == 0 and s.errors == 1
    assert s.marks[0] is Mark.WRONG
    s.type_char("a")
    assert s.pos == 1 and s.marks[0] is Mark.CORRECT


def test_strict_backspace_clears_pending_error():
    s = TypingSession("ab", strict=True, clock=FakeClock())
    s.type_char("X")
    s.backspace()
    assert s.pos == 0 and s.marks[0] is Mark.PENDING


# ---------------------------------------------------------------- инварианты

def test_empty_target_rejected():
    with pytest.raises(ValueError):
        TypingSession("")


def test_marks_and_progress_stay_consistent():
    s = play("привет мир", "привет мир")
    assert all(m is Mark.CORRECT for m in s.marks)
    assert s.metrics().progress == 1.0


def test_multichar_input_ignored():
    s = TypingSession("ab", clock=FakeClock())
    assert s.type_char("ab").accepted is False
    assert s.keystrokes == 0


def test_backspace_at_start_is_noop():
    s = TypingSession("ab", clock=FakeClock())
    assert s.backspace().accepted is False
    assert s.pos == 0


# ------------------------------------------------------------------ профиль

def test_profile_aggregates_across_tests():
    p = Profile()
    for _ in range(3):
        p.absorb(play("abc", "abc", elapsed=1.0))
    assert p.tests == 3
    assert p.total_keystrokes == 9
    assert p.accuracy == 100.0


def test_profile_finds_weak_chars():
    p = Profile()
    for _ in range(5):
        p.absorb(play("aaaz", "aaax"))   # z стабильно мажем
    weak = dict(p.weak_chars())
    assert "z" in weak and weak["z"] == pytest.approx(1.0)
    assert "a" not in weak


def test_profile_ignores_empty_sessions():
    p = Profile()
    p.absorb(TypingSession("abc", clock=FakeClock()))
    assert p.tests == 0
    assert p.accuracy == 100.0


def test_weak_chars_needs_enough_samples():
    """Одна ошибка по редкому символу ещё не делает его слабым."""
    p = Profile()
    p.absorb(play("az", "aX"))
    assert dict(p.weak_chars()).get("z") is None
