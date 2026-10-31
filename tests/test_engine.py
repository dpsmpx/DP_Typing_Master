"""Тесты ядра. Каждый блок закрывает конкретный пункт ревью."""

import pytest

from dp_typing.engine import (
    CHARS_PER_WORD,
    IDLE_GAP,
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


# ------------------------------------------------- простой не считается набором

def test_long_pause_is_not_typing_time():
    """Минута раздумий посреди фразы стоит не дороже IDLE_GAP."""
    clock = FakeClock()
    s = TypingSession("abc", clock=clock)
    s.type_char("a")
    clock.advance(0.2)
    s.type_char("b")
    clock.advance(60)
    s.type_char("c")
    assert s.finished
    assert s.elapsed() == pytest.approx(0.2 + IDLE_GAP)


def test_short_pauses_count_in_full():
    clock = FakeClock()
    s = TypingSession("abc", clock=clock)
    for ch in "abc":
        s.type_char(ch)
        clock.advance(IDLE_GAP - 0.1)
    assert s.elapsed() == pytest.approx(2 * (IDLE_GAP - 0.1))


def test_live_metrics_freeze_while_idle():
    """Пока пользователь отошёл, скорость не падает и время стоит."""
    clock = FakeClock()
    s = TypingSession("abcd", clock=clock)
    s.type_char("a")
    clock.advance(0.5)
    s.type_char("b")
    assert not s.is_idle()
    clock.advance(IDLE_GAP + 1)
    assert s.is_idle()
    frozen = s.elapsed()
    clock.advance(3600)
    assert s.elapsed() == pytest.approx(frozen) == pytest.approx(0.5 + IDLE_GAP)
    s.type_char("c")                       # вернулся — время пошло дальше
    assert not s.is_idle()


def test_backspace_counts_as_activity():
    clock = FakeClock()
    s = TypingSession("abc", clock=clock)
    s.type_char("x")
    clock.advance(IDLE_GAP - 1)
    s.backspace()
    clock.advance(IDLE_GAP - 1)
    s.type_char("a")
    assert s.paused == 0
    assert s.elapsed() == pytest.approx(2 * (IDLE_GAP - 1))


def test_abandoned_test_does_not_bring_idle_hours():
    """Фраза брошена на час: в профиль не должен уйти час «печати»."""
    clock = FakeClock()
    s = TypingSession("abcdef", clock=clock)
    s.type_char("a")
    clock.advance(0.3)
    s.type_char("b")
    clock.advance(3600)
    assert s.elapsed() == pytest.approx(0.3 + IDLE_GAP)


# ------------------------------------------------------------ ё через е

def test_e_is_accepted_for_yo():
    s = TypingSession("ещё всё", equivalents={"ё": "е"})
    for ch in "еще все":
        s.type_char(ch)
    assert s.finished
    assert s.errors == 0
    assert s.combo == len("ещё всё")
    assert s.char_total["ё"] == 2           # статистика — по букве из текста


def test_yo_itself_is_still_correct():
    s = TypingSession("ёж", equivalents={"ё": "е"})
    s.type_char("ё")
    s.type_char("ж")
    assert s.errors == 0


def test_equivalence_is_one_way():
    """«е» вместо «ё» — да, «ё» вместо «е» — нет."""
    s = TypingSession("ель", equivalents={"ё": "е"})
    s.type_char("ё")
    assert s.errors == 1


# --------------------------------------------- брошенная фраза в статистике

def test_absorb_keys_keeps_errors_but_not_the_test():
    s = TypingSession("кот")
    s.type_char("к")
    s.type_char("и")                        # ошибка на «о»
    p = Profile()
    p.absorb_keys(s)
    assert p.tests == 0
    assert p.total_keystrokes == 0
    assert p.total_time == 0
    assert p.char_errors["о"] == 1
    assert p.char_total["к"] == 1


# ------------------------------------------------- рекорды по режимам (A-14)

def finished_session(text: str, seconds_per_char: float) -> TypingSession:
    clock = FakeClock()
    s = TypingSession(text, clock=clock)
    for ch in text:
        s.type_char(ch)
        clock.advance(seconds_per_char)
    return s


def test_records_are_kept_per_key():
    p = Profile()
    p.absorb(finished_session("рад пора пол", 0.1), "ru/lesson/phrase")
    p.absorb(finished_session("обычный текст", 0.3), "ru/common/phrase")
    assert p.record("ru/lesson/phrase") > p.record("ru/common/phrase") > 0
    assert p.record("en/common/phrase") == 0


def test_beating_a_record_is_reported():
    p = Profile()
    assert p.absorb(finished_session("кот", 0.3), "k") is False   # первый — не «рекорд»
    assert p.absorb(finished_session("кот", 0.5), "k") is False   # медленнее
    slow = p.record("k")
    assert p.absorb(finished_session("кот", 0.1), "k") is True
    assert p.record("k") > slow


def test_unfinished_session_sets_no_record():
    s = TypingSession("кот")
    s.type_char("к")
    p = Profile()
    p.absorb(s, "k")
    assert p.records == {}


# ------------------------------------------------- скорость каждой клавиши

def test_session_times_each_correct_keystroke():
    clock = FakeClock()
    s = TypingSession("абв", clock=clock)
    s.type_char("а")            # первое нажатие — интервала ещё нет
    clock.advance(0.2)
    s.type_char("б")
    clock.advance(0.4)
    s.type_char("в")
    assert s.char_time_n == {"б": 1, "в": 1}
    assert s.char_time["б"] == pytest.approx(0.2)
    assert s.char_time["в"] == pytest.approx(0.4)


def test_pauses_and_errors_do_not_time_keys():
    clock = FakeClock()
    s = TypingSession("абв", clock=clock)
    s.type_char("а")
    clock.advance(IDLE_GAP + 3)
    s.type_char("б")            # после простоя — не скорость пальцев
    clock.advance(0.2)
    s.type_char("х")            # ошибка — не засчитываем
    assert s.char_time_n == {}


def test_profile_tracks_key_speed_and_accuracy():
    p = Profile()
    p.absorb(finished_session("абабабаб", 0.25), "k")      # 240 знаков/мин
    assert p.key_speed["б"] == pytest.approx(240, rel=0.01)
    assert p.key_acc["б"] == 1.0
    assert p.key_samples["б"] == 4

    s = TypingSession("бббб")
    for ch in "бхбх":
        s.type_char(ch)
    p.absorb_keys(s)
    assert 0.5 < p.key_acc["б"] < 1.0        # ошибки тянут среднее вниз
    assert p.key_samples["б"] == 8


def test_recent_keystrokes_outweigh_old_ones():
    p = Profile()
    p.absorb(finished_session("б" * 30, 0.6), "k")          # медленно
    p.absorb(finished_session("б" * 30, 0.2), "k")          # быстро
    assert p.key_speed["б"] > (100 + 300) / 2               # ближе к свежему


# ------------------------------------------------------------ тест на время

def test_timed_session_stops_exactly_at_the_limit():
    clock = FakeClock()
    s = TypingSession("а" * 100, clock=clock, time_limit=2.0)
    for moment in (0.0, 0.5, 1.0, 1.5, 1.9):    # пять нажатий внутри лимита
        clock.now = moment
        assert not s.type_char("а").finished
    clock.now = 2.1                              # лимит уже набран
    effect = s.type_char("а")
    assert effect.finished and s.finished and s.timed_out
    assert s.elapsed() == pytest.approx(2.0)    # ровно лимит, не момент проверки
    assert s.keystrokes == 5                    # опоздавшее нажатие не в счёт


def test_timeout_is_found_by_polling():
    clock = FakeClock()
    s = TypingSession("а" * 100, clock=clock, time_limit=1.0)
    s.type_char("а")
    clock.advance(0.7)
    assert not s.check_timeout()
    assert s.remaining() == pytest.approx(0.3)
    clock.advance(0.31)
    assert s.check_timeout()
    assert s.remaining() == 0
    assert not s.check_timeout()                # повторно — уже закончен


def test_pause_does_not_eat_the_time_limit():
    """Отошёл посреди теста на минуту — время теста стоит."""
    clock = FakeClock()
    s = TypingSession("а" * 100, clock=clock, time_limit=10.0)
    s.type_char("а")
    clock.advance(600)
    assert not s.check_timeout()
    assert s.remaining() == pytest.approx(10.0 - IDLE_GAP)


def test_untimed_session_never_times_out():
    clock = FakeClock()
    s = TypingSession("аб", clock=clock)
    s.type_char("а")
    clock.advance(1000)
    assert not s.check_timeout()
    assert s.remaining() is None
