"""Курс по модели keybr: буквы открываются по одной.

Начинаем с шести самых частых букв языка. Новая буква добавляется, когда
каждая уже открытая набирается не медленнее целевой скорости и достаточно
точно (скользящие средние из профиля). Текст — настоящие слова из открытых
букв вперемешку с псевдословами из той же марковской модели, с упором на
«фокусную» букву — ту, что сейчас слабее всех.

Раньше уроки шли четырьмя ступенями по рядам клавиатуры, ступень росла после
одной удачной фразы без учёта скорости (A-15), а на первой ступени вместо
слов выходил случайный набор букв вроде «аопр» (A-16).

Без tkinter — проверяется headless.
"""

from __future__ import annotations

import random
from collections import Counter
from functools import lru_cache

from .engine import CHARS_PER_WORD, Profile
from .layout import LAYOUTS
from .words import load_words, pseudo_word, words_for_zone

#: С какого числа букв начинается курс.
START_LETTERS = 6
#: Сколько нажатий клавиши нужно, чтобы судить о ней.
MIN_SAMPLES = 20
#: Нижняя граница точности клавиши (скользящее среднее).
MIN_ACCURACY = 0.95
#: Варианты целевой скорости, слов в минуту; по умолчанию — как у keybr.
TARGET_SPEEDS_WPM = (25, 35, 45, 60)
DEFAULT_TARGET_WPM = 35
#: Доля настоящих слов в тексте курса (остальное — псевдослова).
REAL_WORD_SHARE = 0.5
#: Насколько охотнее берутся слова с фокусной буквой.
FOCUS_BOOST = 3.0


@lru_cache(maxsize=4)
def letter_order(lang: str) -> str:
    """Буквы языка от самых частых к редким — в этом порядке их открывают.

    «ё» в курсе нет: её засчитывает и «е».
    """
    counts = Counter(ch for word in load_words(lang) for ch in word)
    alphabet = [ch for ch in LAYOUTS[lang].letters if ch.isalpha() and ch != "ё"]
    return "".join(sorted(alphabet, key=lambda ch: (-counts[ch], ch)))


def clamp_unlocked(lang: str, unlocked: object) -> int:
    """Число открытых букв из профиля — в допустимых пределах."""
    total = len(letter_order(lang))
    if not isinstance(unlocked, int) or isinstance(unlocked, bool):
        return START_LETTERS
    return max(START_LETTERS, min(unlocked, total))


def confidence(profile: Profile, ch: str, target_cpm: float) -> float:
    """Насколько клавиша освоена: 1 и больше — освоена.

    Меньшее из двух: скорость относительно цели и точность относительно
    порога. Пока нажатий мало, уверенность не выше их доли от MIN_SAMPLES.
    """
    speed = profile.key_speed.get(ch, 0.0) / target_cpm
    accuracy = profile.key_acc.get(ch, 0.0) / MIN_ACCURACY
    value = min(speed, accuracy)
    samples = profile.key_samples.get(ch, 0)
    if samples < MIN_SAMPLES:
        value = min(value, samples / MIN_SAMPLES)
    return value


def focus_letter(profile: Profile, letters: str, target_cpm: float) -> str:
    """Самая слабая из открытых букв; при равенстве — открытая позже."""
    ranked = sorted(enumerate(letters),
                    key=lambda item: (confidence(profile, item[1], target_cpm), -item[0]))
    return ranked[0][1]


def all_mastered(profile: Profile, letters: str, target_cpm: float) -> bool:
    return all(confidence(profile, ch, target_cpm) >= 1.0 for ch in letters)


def target_cpm(wpm: int) -> float:
    return float(wpm * CHARS_PER_WORD)


def _synthetic(letters: str, focus: str, rng: random.Random) -> str:
    """Запасное «слово», если модель не сложила ничего из этих букв."""
    size = rng.randint(3, 5)
    word = [rng.choice(letters) for _ in range(size)]
    word[rng.randrange(size)] = focus
    return "".join(word)


def course_words(lang: str, letters: str, focus: str, count: int,
                 rng: random.Random) -> list[str]:
    """Слова для курса: только открытые буквы, с упором на фокусную."""
    allowed = frozenset(letters)
    real = words_for_zone(lang, "".join(sorted(allowed)))
    # Пул псевдослов готовится один раз на тест: для теста на две минуты
    # это сотни слов, и тянуть цепь Маркова на каждое заново — лишнее.
    pool_size = min(max(count * 2, 30), 400)
    pseudo = [w for w in (pseudo_word(lang, rng, allowed=allowed, novel=False)
                          for _ in range(pool_size)) if w]
    out: list[str] = []
    for _ in range(count):
        source = real if real and (not pseudo or rng.random() < REAL_WORD_SHARE) else pseudo
        if not source:
            out.append(_synthetic(letters, focus, rng))
            continue
        candidates = rng.choices(source, k=4)
        weights = [1.0 + FOCUS_BOOST * word.count(focus) for word in candidates]
        out.append(rng.choices(candidates, weights=weights, k=1)[0])
    return out
