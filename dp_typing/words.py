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
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache

from .layout import EQUIVALENTS, LAYOUTS

MIN_WORD_LEN = 2
MAX_WORD_LEN = 12
#: Псевдослово короче трёх букв — это обрывок вроде «ch» или «те», а не слово.
MIN_PSEUDO_LEN = 3


class Mode(str, Enum):
    LESSON = "lesson"
    COMMON = "common"
    PSEUDO = "pseudo"
    ADAPTIVE = "adaptive"
    CUSTOM = "custom"

    @property
    def title(self) -> str:
        return _MODE_TITLES[self]


_MODE_TITLES = {
    Mode.LESSON: "Уроки",
    Mode.COMMON: "Частотные слова",
    Mode.PSEUDO: "Псевдослова",
    Mode.ADAPTIVE: "Слабые клавиши",
    Mode.CUSTOM: "Свой текст",
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


@lru_cache(maxsize=4)
def _real_words(lang: str) -> frozenset[str]:
    return frozenset(load_words(lang))


def _walk(model, rng: random.Random, allowed: frozenset[str] | None) -> str:
    """Один проход по марковской цепи; ``allowed`` ограничивает буквы."""
    prev = cur = "\x02"
    out: list[str] = []
    while len(out) < MAX_WORD_LEN:
        choices = model.get((prev, cur))
        if choices is None:
            break
        chars, weights = choices
        if allowed is not None:
            pairs = [(c, w) for c, w in zip(chars, weights) if c == "\x03" or c in allowed]
            if not pairs:
                break
            chars, weights = zip(*pairs)
        ch = rng.choices(chars, weights=weights, k=1)[0]
        if ch == "\x03":
            break
        out.append(ch)
        prev, cur = cur, ch
    return "".join(out)


def pseudo_word(lang: str, rng: random.Random, *, allowed: frozenset[str] | None = None,
                novel: bool = True) -> str:
    """Сгенерировать произносимое псевдослово по статистике реального языка.

    ``novel`` — не отдавать настоящие слова: режим обещает несуществующие,
    а раньше каждое седьмое «псевдослово» было обычным «мой» или «day».
    ``allowed`` — только эти буквы (для курса). Пустая строка — не вышло.
    """
    model = _markov(lang)
    real = _real_words(lang) if novel else frozenset()
    fallback = ""
    for _ in range(64):  # обычно хватает 1-3 попыток
        word = _walk(model, rng, allowed)
        if MIN_PSEUDO_LEN <= len(word) <= MAX_WORD_LEN:
            if word not in real:
                return word
            fallback = fallback or word
    if fallback or allowed is not None:
        return fallback
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
    """Слова, целиком укладывающиеся в заданный набор клавиш.

    Символ с эквивалентом считается доступным, если доступен эквивалент:
    слово «ещё» годится для зоны с «е», ведь «е» засчитывается вместо «ё».
    """
    zone = set(allowed)
    alternatives = EQUIVALENTS.get(lang, {})

    def fits(word: str) -> bool:
        return all(
            ch in zone or any(alt in zone for alt in alternatives.get(ch, ""))
            for ch in word
        )

    return tuple(w for w in load_words(lang) if fits(w))


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


# --------------------------------------------- заглавные, знаки, цифры

@dataclass(frozen=True)
class TextOptions:
    """Что добавить к словам, чтобы текст был похож на настоящий (A-27)."""

    caps: bool = False      # заглавные: начало предложения и изредка внутри
    punct: bool = False     # знаки препинания, скобки, кавычки, тире
    digits: bool = False    # числа вместо части слов

    @property
    def any(self) -> bool:
        return self.caps or self.punct or self.digits

    @property
    def key(self) -> str:
        """Короткая метка для ключа рекорда: «A.1» — всё включено."""
        return "".join(mark for mark, on in (("A", self.caps), (".", self.punct),
                                             ("1", self.digits)) if on)


#: Вероятности — на одно слово. Подобраны так, чтобы текст читался как
#: обычный: запятая каждые 6-7 слов, предложение в 4-9 слов.
P_COMMA = 0.15
P_RARE_MARK = 0.03      # «:» или «;» вместо запятой
P_DASH = 0.04
P_BRACKETS = 0.03
P_QUOTES = 0.03
P_CAPITAL = 0.10        # заглавная внутри предложения (имена, названия)
P_NUMBER = 0.15
SENTENCE_WORDS = (4, 9)


def number_token(rng: random.Random) -> str:
    """Число, какие встречаются в тексте: 7, 42, 350, 2024."""
    roll = rng.random()
    if roll < 0.45:
        return str(rng.randint(0, 99))
    if roll < 0.8:
        return str(rng.randint(100, 9999))
    return str(rng.randint(1900, 2030))


def decorate(words: Sequence[str], rng: random.Random, options: TextOptions) -> list[str]:
    """Превратить список слов в текст с заглавными, знаками и цифрами.

    Число слов (токенов через пробел) сохраняется — важно для тестов «на N
    слов»: число заменяет слово, тире добавляется к слову через пробел.
    """
    if not options.any:
        return list(words)
    out: list[str] = []
    left = rng.randint(*SENTENCE_WORDS)
    sentence_start = True
    last = len(words) - 1
    for i, word in enumerate(words):
        if options.digits and rng.random() < P_NUMBER:
            word = number_token(rng)
        elif options.caps and (sentence_start or rng.random() < P_CAPITAL):
            word = word[:1].upper() + word[1:]
        sentence_start = False
        if options.punct:
            roll = rng.random()
            if roll < P_BRACKETS:
                word = f"({word})"
            elif roll < P_BRACKETS + P_QUOTES:
                word = f'"{word}"'
            left -= 1
            if left <= 0 or i == last:
                word += rng.choices(".!?", weights=(14, 3, 3))[0]
                left = rng.randint(*SENTENCE_WORDS)
                sentence_start = True
            elif rng.random() < P_COMMA:
                word += "," if rng.random() > P_RARE_MARK / P_COMMA else rng.choice(":;")
            elif rng.random() < P_DASH:
                word += " -"
        out.append(word)
    return out


# ------------------------------------------------------------ длина теста

#: Слов в «фразе» — классическом коротком тесте.
PHRASE_WORDS = 9
#: Сколько слов готовить на секунду теста на время. Потолок скорости —
#: 1500 знаков/мин = 25 знаков/с, средняя длина слова с пробелом — 6-7
#: знаков: 4.2 слова в секунду с запасом не кончатся раньше времени.
WORDS_PER_SECOND = 4.2


@dataclass(frozen=True)
class Length:
    """Длина теста: одна фраза, N слов или N секунд (Monkeytype, TIPP10)."""

    kind: str           # "phrase", "words" или "time"
    amount: int = 0

    @property
    def key(self) -> str:
        """Метка для профиля и ключа рекорда: phrase, w25, t60."""
        return "phrase" if self.kind == "phrase" else f"{self.kind[0]}{self.amount}"

    @property
    def title(self) -> str:
        if self.kind == "words":
            return f"{self.amount} СЛОВ"
        if self.kind == "time":
            return f"{self.amount} С"
        return "ФРАЗА"

    @property
    def timed(self) -> bool:
        return self.kind == "time"

    def word_count(self) -> int:
        """Сколько слов сгенерировать для теста такой длины."""
        if self.kind == "words":
            return self.amount
        if self.kind == "time":
            return int(self.amount * WORDS_PER_SECOND) + 5
        return PHRASE_WORDS

    @classmethod
    def parse(cls, key: object) -> Length:
        """Обратно из метки; неизвестное — фраза (профиль мог быть испорчен)."""
        for length in LENGTHS:
            if length.key == key:
                return length
        return LENGTHS[0]


LENGTHS: tuple[Length, ...] = (
    Length("phrase"),
    *(Length("words", n) for n in (10, 25, 50, 100)),
    *(Length("time", n) for n in (15, 30, 60, 120)),
)


# --------------------------------------------------------------- фасад

class TextSource:
    """Выдаёт фразы по текущему режиму, языку и ступени урока."""

    def __init__(self, lang: str = "ru", mode: Mode = Mode.COMMON,
                 stage: int = 0, rng: random.Random | None = None,
                 options: TextOptions | None = None) -> None:
        self.lang = lang
        self.mode = mode
        self.stage = stage
        self.rng = rng or random.Random()
        self.options = options or TextOptions()

    @property
    def decorates(self) -> bool:
        """Опции текста — только для генерируемых слов: в уроках свои ступени
        клавиш, а свой текст уже содержит и заглавные, и знаки."""
        return self.mode in (Mode.COMMON, Mode.PSEUDO, Mode.ADAPTIVE) and self.options.any

    @property
    def stage_title(self) -> str:
        stages = lesson_stages(self.lang)
        return stages[min(self.stage, len(stages) - 1)][0]

    def phrase(self, word_count: int = 9, weak: Sequence[tuple[str, float]] = ()) -> str:
        """Собрать фразу из ``word_count`` слов."""
        words = self._pick(word_count, weak)
        if self.decorates:
            words = decorate(words, self.rng, self.options)
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
