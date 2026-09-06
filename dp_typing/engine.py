"""Ядро тренажёра: состояние теста, метрики и комбо.

Модуль намеренно не импортирует tkinter — вся логика проверяется headless,
без дисплея. UI только отображает то, что посчитано здесь.
"""

from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass
from enum import IntEnum
from typing import Callable

#: Нижняя граница измеряемого времени — защита от деления на ноль.
MIN_ELAPSED = 0.05

#: Потолок скорости. Мировой рекорд — около 1100 знаков/мин, так что всё выше
#: это вставка из буфера или залипшая клавиша, а не человек. Без потолка
#: мгновенный ввод давал бы десятки тысяч (см. ревью, п. 5).
MAX_CPM = 1500.0

#: Общепринятая условная длина «слова» для WPM.
CHARS_PER_WORD = 5

#: Сколько раз символ должен встретиться, прежде чем считать его статистику
#: значимой для адаптивного режима.
MIN_SAMPLES_FOR_WEAKNESS = 4


class Mark(IntEnum):
    """Состояние одной позиции в целевом тексте."""

    PENDING = 0
    CORRECT = 1
    WRONG = 2


@dataclass(frozen=True)
class KeyEffect:
    """Что именно изменилось от одного нажатия.

    UI перерисовывает только позиции из ``changed`` — это и даёт O(1) на
    нажатие вместо перерисовки всей строки.
    """

    accepted: bool = False
    changed: tuple[int, ...] = ()
    correct: bool = False
    combo_gained: bool = False
    combo_broken: bool = False
    finished: bool = False
    started: bool = False

    #: Неизменяемый синглтон для «нажатие проигнорировано».
    @staticmethod
    def ignored() -> KeyEffect:
        return _IGNORED


_IGNORED = KeyEffect()


@dataclass(frozen=True)
class Metrics:
    """Снимок метрик теста."""

    elapsed: float
    cpm: float
    wpm: float
    raw_wpm: float
    accuracy: float
    errors: int
    keystrokes: int
    correct_chars: int
    combo: int
    best_combo: int
    progress: float


class TypingSession:
    """Один тест: целевая строка, позиция курсора, счётчики и время.

    Часы инжектируются (``clock``), чтобы тесты были детерминированными.
    По умолчанию — ``time.perf_counter``: монотонный, в отличие от
    ``time.time``, который может прыгнуть при синхронизации по NTP.
    """

    __slots__ = (
        "_clock",
        "best_combo",
        "char_errors",
        "char_total",
        "combo",
        "correct_chars",
        "corrections",
        "errors",
        "finished_at",
        "keystrokes",
        "marks",
        "pos",
        "started_at",
        "strict",
        "target",
    )

    def __init__(
        self,
        target: str,
        *,
        strict: bool = False,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        if not target:
            raise ValueError("target не может быть пустым")
        self.target = target
        self.strict = strict
        self._clock = clock
        self.marks: list[Mark] = [Mark.PENDING] * len(target)
        self.pos = 0
        self.keystrokes = 0
        self.errors = 0
        self.corrections = 0
        self.correct_chars = 0
        self.combo = 0
        self.best_combo = 0
        self.started_at: float | None = None
        self.finished_at: float | None = None
        # Посимвольная статистика — основа адаптивного подбора слов.
        self.char_total: Counter[str] = Counter()
        self.char_errors: Counter[str] = Counter()

    # ------------------------------------------------------------------ ввод

    @property
    def finished(self) -> bool:
        return self.finished_at is not None

    @property
    def started(self) -> bool:
        return self.started_at is not None

    def type_char(self, ch: str) -> KeyEffect:
        """Обработать один печатный символ."""
        if self.finished or len(ch) != 1:
            return _IGNORED

        started = False
        if self.started_at is None:
            self.started_at = self._clock()
            started = True

        idx = self.pos
        expected = self.target[idx]
        correct = ch == expected

        self.keystrokes += 1
        self.char_total[expected] += 1

        if correct:
            self.marks[idx] = Mark.CORRECT
            self.correct_chars += 1
            self.pos += 1
            self.combo += 1
            if self.combo > self.best_combo:
                self.best_combo = self.combo
            combo_gained, combo_broken = True, False
        else:
            self.errors += 1
            self.char_errors[expected] += 1
            self.marks[idx] = Mark.WRONG
            if not self.strict:
                # Свободный режим: курсор идёт дальше, ошибка остаётся видимой.
                self.pos += 1
            combo_gained = False
            combo_broken = self.combo > 0
            self.combo = 0

        finished = self.pos >= len(self.target)
        if finished:
            self.finished_at = self._clock()

        return KeyEffect(
            accepted=True,
            changed=(idx,),
            correct=correct,
            combo_gained=combo_gained,
            combo_broken=combo_broken,
            finished=finished,
            started=started,
        )

    def backspace(self) -> KeyEffect:
        """Стереть один символ назад."""
        if self.finished:
            return _IGNORED

        # Строгий режим: на текущей позиции висит непринятая ошибка — гасим её,
        # курсор при этом не двигаем.
        if self.strict and self.pos < len(self.marks) and self.marks[self.pos] is Mark.WRONG:
            self.marks[self.pos] = Mark.PENDING
            self.corrections += 1
            return KeyEffect(accepted=True, changed=(self.pos,))

        if self.pos == 0:
            return _IGNORED

        self.pos -= 1
        idx = self.pos
        was = self.marks[idx]
        self.marks[idx] = Mark.PENDING
        self.corrections += 1

        combo_broken = False
        if was is Mark.CORRECT:
            self.correct_chars -= 1
            # Иначе «набрал — стёр — набрал» бесконечно накручивало бы комбо.
            if self.combo > 0:
                self.combo -= 1
                combo_broken = True
        return KeyEffect(accepted=True, changed=(idx,), combo_broken=combo_broken)

    # --------------------------------------------------------------- метрики

    def elapsed(self, now: float | None = None) -> float:
        if self.started_at is None:
            return 0.0
        end = self.finished_at
        if end is None:
            end = self._clock() if now is None else now
        return max(end - self.started_at, 0.0)

    def metrics(self, now: float | None = None) -> Metrics:
        elapsed = self.elapsed(now)
        minutes = max(elapsed, MIN_ELAPSED) / 60.0
        cpm = min(self.correct_chars / minutes, MAX_CPM)
        raw_cpm = min(self.keystrokes / minutes, MAX_CPM)
        accuracy = (
            100.0
            if self.keystrokes == 0
            else max(0.0, (self.keystrokes - self.errors) / self.keystrokes * 100.0)
        )
        return Metrics(
            elapsed=elapsed,
            cpm=cpm,
            wpm=cpm / CHARS_PER_WORD,
            raw_wpm=raw_cpm / CHARS_PER_WORD,
            accuracy=accuracy,
            errors=self.errors,
            keystrokes=self.keystrokes,
            correct_chars=self.correct_chars,
            combo=self.combo,
            best_combo=self.best_combo,
            progress=self.pos / len(self.target),
        )


class Profile:
    """Накопительная статистика за всю сессию.

    Живёт дольше отдельного теста: копит посимвольные ошибки (для адаптивного
    режима) и агрегаты для итоговой панели.
    """

    __slots__ = (
        "best_combo",
        "best_wpm",
        "char_errors",
        "char_total",
        "tests",
        "total_errors",
        "total_keystrokes",
        "total_time",
    )

    def __init__(self) -> None:
        self.char_total: Counter[str] = Counter()
        self.char_errors: Counter[str] = Counter()
        self.tests = 0
        self.total_keystrokes = 0
        self.total_errors = 0
        self.total_time = 0.0
        self.best_combo = 0
        self.best_wpm = 0.0

    def absorb(self, session: TypingSession) -> None:
        """Влить результаты завершённого (или прерванного) теста."""
        if session.keystrokes == 0:
            return
        self.char_total.update(session.char_total)
        self.char_errors.update(session.char_errors)
        self.tests += 1
        self.total_keystrokes += session.keystrokes
        self.total_errors += session.errors
        self.total_time += session.elapsed()
        m = session.metrics()
        self.best_combo = max(self.best_combo, session.best_combo)
        if session.finished:
            self.best_wpm = max(self.best_wpm, m.wpm)

    @property
    def accuracy(self) -> float:
        if self.total_keystrokes == 0:
            return 100.0
        return (self.total_keystrokes - self.total_errors) / self.total_keystrokes * 100.0

    @property
    def wpm(self) -> float:
        """Средняя скорость за всю историю, с тем же потолком, что и у теста."""
        if self.total_time <= 0:
            return 0.0
        correct = self.total_keystrokes - self.total_errors
        cpm = min(correct / (self.total_time / 60.0), MAX_CPM)
        return cpm / CHARS_PER_WORD

    def weak_chars(self, limit: int = 8) -> list[tuple[str, float]]:
        """Символы с наибольшей долей ошибок — по убыванию «проблемности»."""
        out = []
        for ch, total in self.char_total.items():
            if total < MIN_SAMPLES_FOR_WEAKNESS or not ch.strip():
                continue
            rate = self.char_errors.get(ch, 0) / total
            if rate > 0:
                out.append((ch, rate))
        out.sort(key=lambda p: (-p[1], p[0]))
        return out[:limit]
