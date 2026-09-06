"""Источники тренировочного текста.

Четыре режима, от простого к сложному:

* ``LESSON``   — уроки по зонам клавиатуры (домашний ряд → верхний → нижний);
* ``COMMON``   — частотная лексика языка, реальные слова;
* ``PSEUDO``   — псевдослова из марковской модели, обученной на той же лексике;
* ``ADAPTIVE`` — реальные слова, смещённые к клавишам, на которых вы ошибаетесь.

``ADAPTIVE`` — главный аргумент в пользу эффективности: тренажёр сам находит
слабые клавиши и подсовывает их чаще.
"""

from __future__ import annotations

import random
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Sequence
from enum import Enum
from functools import lru_cache

from .layout import LAYOUTS

MIN_WORD_LEN = 2
MAX_WORD_LEN = 12


class Mode(str, Enum):
    LESSON = "lesson"
    COMMON = "common"
    PSEUDO = "pseudo"
    ADAPTIVE = "adaptive"

    @property
    def title(self) -> str:
        return _MODE_TITLES[self]


_MODE_TITLES = {
    Mode.LESSON: "Уроки",
    Mode.COMMON: "Частотные слова",
    Mode.PSEUDO: "Псевдослова",
    Mode.ADAPTIVE: "Слабые клавиши",
}


# --------------------------------------------------------------- словари

@lru_cache(maxsize=4)
def load_words(lang: str) -> tuple[str, ...]:
    """Прочитать список слов из пакета. Кэшируется — файл читается один раз."""
    from importlib.resources import files

    name = {"ru": "ru_common.txt", "en": "en_common.txt"}.get(lang)
    if name is None:
        raise ValueError(f"неизвестный язык: {lang!r}")
    raw = (files("dp_typing.data") / name).read_text(encoding="utf-8")
    return tuple(
        w for w in (unicodedata.normalize("NFC", line.strip()) for line in raw.splitlines()) if w
    )


# ------------------------------------------------- марковская модель слов

@lru_cache(maxsize=4)
def _markov(lang: str) -> dict[tuple[str, str], tuple[tuple[str, ...], tuple[int, ...]]]:
    """Триграммная модель символов: (c1, c2) -> (варианты, веса).

    Веса заранее разложены в кортежи, чтобы ``random.choices`` не пересобирал
    их на каждом слове.
    """
    counts: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    for word in load_words(lang):
        seq = ("\x02", "\x02", *word, "\x03")
        for i in range(len(seq) - 2):
            counts[(seq[i], seq[i + 1])][seq[i + 2]] += 1
    return {key: (tuple(c.keys()), tuple(c.values())) for key, c in counts.items()}


def pseudo_word(lang: str, rng: random.Random) -> str:
    """Сгенерировать произносимое псевдослово по статистике реального языка."""
    model = _markov(lang)
    for _ in range(24):  # практически всегда хватает 1-2 попыток
        prev, cur = "\x02", "\x02"
        out: list[str] = []
        while len(out) < MAX_WORD_LEN:
            choices = model.get((prev, cur))
            if choices is None:
                break
            ch = rng.choices(choices[0], weights=choices[1], k=1)[0]
            if ch == "\x03":
                break
            out.append(ch)
            prev, cur = cur, ch
        if MIN_WORD_LEN <= len(out) <= MAX_WORD_LEN:
            return "".join(out)
    # Модель упёрлась в тупик — отдаём реальное слово, лишь бы не пустоту.
    return rng.choice(load_words(lang))


# ------------------------------------------------------------ уроки по зонам

@lru_cache(maxsize=8)
def lesson_stages(lang: str) -> tuple[tuple[str, str], ...]:
    """Ступени уроков: (название, разрешённые символы), от простого к полному."""
    layout = LAYOUTS[lang]
    home, top = layout.home, layout.top
    mid = len(home) // 2
    # Каждая ступень строго включает предыдущую: пройденные клавиши
    # никогда не исчезают из тренировки.
    return (
        ("Центр домашнего ряда", home[mid - 2 : mid + 2]),
        ("Домашний ряд", home),
        ("Домашний + верхний", home + top),
        ("Весь алфавит", layout.letters),
    )


@lru_cache(maxsize=32)
def words_for_zone(lang: str, allowed: str) -> tuple[str, ...]:
    """Слова, целиком укладывающиеся в заданный набор клавиш."""
    zone = set(allowed)
    return tuple(w for w in load_words(lang) if zone.issuperset(w))


def _synthetic_zone_words(allowed: str, rng: random.Random, count: int) -> list[str]:
    """Запасной вариант для узких зон, где реальных слов почти нет."""
    keys = sorted(set(allowed))
    return ["".join(rng.choice(keys) for _ in range(rng.randint(3, 5))) for _ in range(count)]


# ---------------------------------------------------------- адаптивный отбор

def adaptive_weights(
    words: Sequence[str], weak: Sequence[tuple[str, float]], boost: float = 6.0
) -> list[float]:
    """Вес слова тем выше, чем больше в нём проблемных для пользователя букв."""
    if not weak:
        return [1.0] * len(words)
    rates = dict(weak)
    return [
        1.0 + boost * sum(rates.get(ch, 0.0) for ch in set(word))
        for word in words
    ]


# --------------------------------------------------------------- фасад

class TextSource:
    """Выдаёт фразы по текущему режиму, языку и ступени урока."""

    def __init__(self, lang: str = "ru", mode: Mode = Mode.COMMON,
                 stage: int = 0, rng: random.Random | None = None) -> None:
        self.lang = lang
        self.mode = mode
        self.stage = stage
        self.rng = rng or random.Random()

    @property
    def stage_title(self) -> str:
        stages = lesson_stages(self.lang)
        return stages[min(self.stage, len(stages) - 1)][0]

    def phrase(self, word_count: int = 9, weak: Sequence[tuple[str, float]] = ()) -> str:
        """Собрать фразу из ``word_count`` слов."""
        words = self._pick(word_count, weak)
        return " ".join(words)

    def _pick(self, n: int, weak: Sequence[tuple[str, float]]) -> list[str]:
        rng = self.rng
        if self.mode is Mode.PSEUDO:
            return [pseudo_word(self.lang, rng) for _ in range(n)]

        if self.mode is Mode.LESSON:
            stages = lesson_stages(self.lang)
            allowed = stages[min(self.stage, len(stages) - 1)][1]
            pool = words_for_zone(self.lang, allowed)
            if len(pool) < 8:
                return _synthetic_zone_words(allowed, rng, n)
            return rng.choices(pool, k=n)

        pool = load_words(self.lang)
        if self.mode is Mode.ADAPTIVE and weak:
            return rng.choices(pool, weights=adaptive_weights(pool, weak), k=n)
        return rng.choices(pool, k=n)
