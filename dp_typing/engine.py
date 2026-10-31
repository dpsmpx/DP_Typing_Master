"""Ядро тренажёра: состояние теста, метрики и комбо.

Модуль намеренно не импортирует tkinter — вся логика проверяется headless,
без дисплея. UI только отображает то, что посчитано здесь.
"""

from __future__ import annotations

import time
from collections import Counter
from collections.abc import Mapping
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

#: Простой дольше этого не считается временем набора: таймер «засыпает» через
#: столько секунд без нажатий и просыпается со следующим. Иначе телефонный
#: звонок посреди фразы обваливал её скорость, а брошенная фраза при выходе
#: приносила в профиль часы «печати».
IDLE_GAP = 5.0

#: Вес одного нажатия в скользящем среднем скорости и точности клавиши:
#: последние ~20 нажатий значат больше, чем вся история. На этом держится
#: курс (ступень растёт, когда каждая клавиша достаточно быстра и точна).
KEY_EMA_ALPHA = 0.1


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

    ``equivalents`` — какие нажатия засчитываются вместо символа цели:
    ``{"ё": "е"}`` разрешает печатать «е» там, где в слове «ё».
    """

    __slots__ = (
        "_clock",
        "_last_at",
        "best_combo",
        "char_errors",
        "char_time",
        "char_time_n",
        "char_total",
        "combo",
        "correct_chars",
        "corrections",
        "equivalents",
        "errors",
        "finished_at",
        "keystrokes",
        "marks",
        "paused",
        "pos",
        "started_at",
        "strict",
        "target",
        "time_limit",
        "timed_out",
    )

    def __init__(
        self,
        target: str,
        *,
        strict: bool = False,
        clock: Callable[[], float] = time.perf_counter,
        equivalents: Mapping[str, str] | None = None,
        time_limit: float | None = None,
    ) -> None:
        if not target:
            raise ValueError("target не может быть пустым")
        self.target = target
        self.strict = strict
        self._clock = clock
        self.equivalents: dict[str, str] = dict(equivalents or {})
        #: Тест на время: столько секунд набора (паузы не в счёт), потом — финиш.
        self.time_limit = time_limit
        self.timed_out = False
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
        self._last_at = 0.0
        #: Сумма простоев сверх IDLE_GAP — вычитается из времени набора.
        self.paused = 0.0
        # Посимвольная статистика — основа адаптивного подбора слов.
        self.char_total: Counter[str] = Counter()
        self.char_errors: Counter[str] = Counter()
        # Время до верного нажатия по символам: сумма интервалов и их число.
        self.char_time: Counter[str] = Counter()
        self.char_time_n: Counter[str] = Counter()

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

        now = self._clock()
        if self.check_timeout(now):
            # Время вышло раньше, чем пришло нажатие: оно уже не в счёт.
            return KeyEffect(accepted=True, finished=True)
        started = self.started_at is None
        gap: float | None = None
        if started:
            self.started_at = self._last_at = now
        else:
            gap = now - self._last_at
            self._note_activity(now)

        idx = self.pos
        expected = self.target[idx]
        correct = ch == expected or ch in self.equivalents.get(expected, "")

        self.keystrokes += 1
        self.char_total[expected] += 1

        if correct:
            if gap is not None and gap <= IDLE_GAP:
                # Скорость конкретной клавиши: сколько от прошлого нажатия
                # до этого. Паузы длиннее IDLE_GAP — не про пальцы.
                self.char_time[expected] += gap
                self.char_time_n[expected] += 1
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
            self.finished_at = now

        return KeyEffect(
            accepted=True,
            changed=(idx,),
            correct=correct,
            combo_gained=combo_gained,
            combo_broken=combo_broken,
            finished=finished,
            started=started,
        )

    def _note_activity(self, now: float) -> None:
        """Учесть нажатие: простой сверх IDLE_GAP уходит в паузу."""
        gap = now - self._last_at
        if gap > IDLE_GAP:
            self.paused += gap - IDLE_GAP
        self._last_at = now

    def backspace(self) -> KeyEffect:
        """Стереть один символ назад."""
        if self.finished:
            return _IGNORED
        if self.started_at is not None:
            self._note_activity(self._clock())

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
        """Время набора без простоев (см. IDLE_GAP)."""
        if self.started_at is None:
            return 0.0
        end = self.finished_at
        idle = 0.0
        if end is None:
            end = self._clock() if now is None else now
            idle = max(end - self._last_at - IDLE_GAP, 0.0)  # идущий сейчас простой
        return max(end - self.started_at - self.paused - idle, 0.0)

    def check_timeout(self, now: float | None = None) -> bool:
        """Закончить тест на время, если лимит набран. True — только что закончен.

        Финиш ставится ровно на момент, когда лимит был достигнут, а не на
        момент проверки: таймер интерфейса тикает раз в 200 мс, и иначе тест
        «на 30 секунд» длился бы до 30,2 с.
        """
        if (self.time_limit is None or self.finished_at is not None
                or self.started_at is None):
            return False
        if self.elapsed(now) < self.time_limit:
            return False
        self.finished_at = self.started_at + self.paused + self.time_limit
        self.timed_out = True
        return True

    def remaining(self, now: float | None = None) -> float | None:
        """Сколько секунд осталось в тесте на время (None — тест не на время)."""
        if self.time_limit is None:
            return None
        return max(self.time_limit - self.elapsed(now), 0.0)

    def is_idle(self, now: float | None = None) -> bool:
        """Тест начат, не закончен, и нажатий не было дольше IDLE_GAP."""
        if self.started_at is None or self.finished_at is not None:
            return False
        now = self._clock() if now is None else now
        return now - self._last_at > IDLE_GAP

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


def _blend(old: float | None, new: float, samples: int) -> float:
    """Скользящее среднее: ``samples`` нажатий с весом KEY_EMA_ALPHA каждое."""
    if old is None:
        return new
    keep = (1.0 - KEY_EMA_ALPHA) ** samples
    return old * keep + new * (1.0 - keep)


class Profile:
    """Накопительная статистика за всю историю.

    Живёт дольше отдельного теста: копит посимвольные ошибки (для адаптивного
    режима), скорость и точность каждой клавиши (для курса), рекорды по
    языку и режиму и агрегаты для итоговой панели.
    """

    __slots__ = (
        "best_combo",
        "char_errors",
        "char_total",
        "key_acc",
        "key_samples",
        "key_speed",
        "records",
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
        #: Рекорды скорости (слов/мин) по ключу «язык/режим/длина/опции».
        #: Общий рекорд был нечестным: фраза урока «рад пора пол» ставила
        #: рекорд, недостижимый на обычном тексте (аудит, A-14).
        self.records: dict[str, float] = {}
        #: Скользящие средние по клавише: скорость (знаков/мин) и точность (0..1).
        self.key_speed: dict[str, float] = {}
        self.key_acc: dict[str, float] = {}
        self.key_samples: Counter[str] = Counter()

    def absorb_keys(self, session: TypingSession) -> None:
        """Влить только посимвольную статистику — для брошенной фразы.

        Пропущенная (Esc) или недобранная фраза не засчитывается как тест и не
        влияет на скорость, но её нажатия — ценные данные о клавишах.
        """
        self.char_total.update(session.char_total)
        self.char_errors.update(session.char_errors)
        for ch, n in session.char_time_n.items():
            spent = session.char_time[ch]
            if n and spent > 0 and ch.strip():
                cpm = min(60.0 * n / spent, MAX_CPM)
                self.key_speed[ch] = _blend(self.key_speed.get(ch), cpm, n)
        for ch, total in session.char_total.items():
            if total and ch.strip():
                acc = 1.0 - session.char_errors.get(ch, 0) / total
                self.key_acc[ch] = _blend(self.key_acc.get(ch), acc, total)
                self.key_samples[ch] += total

    def absorb(self, session: TypingSession, record_key: str | None = None) -> bool:
        """Влить результаты теста целиком.

        Возвращает True, если побит прежний рекорд по ``record_key`` (первый
        результат в новом режиме рекордом не объявляется — побивать нечего).
        """
        if session.keystrokes == 0:
            return False
        self.absorb_keys(session)
        self.tests += 1
        self.total_keystrokes += session.keystrokes
        self.total_errors += session.errors
        self.total_time += session.elapsed()
        self.best_combo = max(self.best_combo, session.best_combo)
        if not session.finished or record_key is None:
            return False
        wpm = session.metrics().wpm
        previous = self.records.get(record_key)
        if previous is None or wpm > previous:
            self.records[record_key] = wpm
        return previous is not None and wpm > previous

    def record(self, record_key: str) -> float:
        """Рекорд по ключу или 0, если в этом режиме ещё не печатали."""
        return self.records.get(record_key, 0.0)

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
