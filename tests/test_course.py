"""Курс по модели keybr: порядок букв, уверенность, фокус, текст (A-15, A-16)."""

import random

import pytest

from dp_typing.course import (
    MIN_ACCURACY,
    MIN_SAMPLES,
    START_LETTERS,
    all_mastered,
    clamp_unlocked,
    confidence,
    course_words,
    focus_letter,
    letter_order,
    target_cpm,
)
from dp_typing.engine import Profile
from dp_typing.layout import LAYOUTS
from dp_typing.words import Mode, TextSource

TARGET = target_cpm(35)


def trained(**keys) -> Profile:
    """Профиль, где клавиша набирается с заданной скоростью и точностью."""
    p = Profile()
    for ch, (speed, acc, samples) in keys.items():
        p.key_speed[ch], p.key_acc[ch], p.key_samples[ch] = speed, acc, samples
    return p


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_order_covers_the_alphabet_by_frequency(lang):
    order = letter_order(lang)
    alphabet = {ch for ch in LAYOUTS[lang].letters if ch.isalpha()} - {"ё"}
    assert set(order) == alphabet and len(order) == len(alphabet)
    assert order[0] in "оеаe"                  # самые частые — гласные


def test_frequent_letters_come_first():
    assert set(letter_order("ru")[:START_LETTERS]) == set("оеаитн")
    assert letter_order("ru").index("ф") > letter_order("ru").index("к")


def test_confidence_needs_speed_accuracy_and_samples():
    assert confidence(trained(а=(TARGET, 1.0, 100)), "а", TARGET) >= 1
    assert confidence(trained(а=(TARGET / 2, 1.0, 100)), "а", TARGET) == pytest.approx(0.5)
    assert confidence(trained(а=(TARGET * 2, 0.8, 100)), "а", TARGET) < 1
    assert confidence(trained(а=(TARGET * 2, 1.0, MIN_SAMPLES // 2)), "а", TARGET) == 0.5
    assert confidence(Profile(), "а", TARGET) == 0


def test_focus_is_the_weakest_letter():
    p = trained(а=(TARGET, 1, 99), б=(TARGET / 3, 1, 99), в=(TARGET / 2, 1, 99))
    assert focus_letter(p, "абв", TARGET) == "б"


def test_ties_focus_on_the_newest_letter():
    """Новая буква без нажатий — фокус на ней, а не на первой из старых."""
    assert focus_letter(Profile(), "абв", TARGET) == "в"


def test_all_mastered_requires_every_letter():
    good = (TARGET * 1.1, MIN_ACCURACY + 0.01, MIN_SAMPLES)
    assert all_mastered(trained(а=good, б=good), "аб", TARGET)
    assert not all_mastered(trained(а=good), "аб", TARGET)


def test_unlocked_count_is_clamped():
    total = len(letter_order("ru"))
    assert clamp_unlocked("ru", None) == START_LETTERS
    assert clamp_unlocked("ru", 2) == START_LETTERS
    assert clamp_unlocked("ru", 999) == total
    assert clamp_unlocked("ru", True) == START_LETTERS
    assert clamp_unlocked("ru", 10) == 10


@pytest.mark.parametrize("lang", ["ru", "en"])
@pytest.mark.parametrize("unlocked", [START_LETTERS, 10, 20])
def test_course_text_uses_only_open_letters(lang, unlocked):
    letters = letter_order(lang)[:unlocked]
    words = course_words(lang, letters, letters[-1], 200, random.Random(unlocked))
    used = set("".join(words)) - {"ё"}               # «ё» печатают через «е»
    assert used <= set(letters), f"лишние буквы {used - set(letters)}"
    assert all(len(w) >= 2 for w in words)


def test_course_text_leans_on_the_focus_letter():
    letters = letter_order("ru")[:10]
    focus = letters[-1]
    rng = random.Random(1)
    with_focus = sum(focus in w for w in course_words("ru", letters, focus, 400, rng))
    plain = sum(letters[0] in w for w in course_words("ru", letters, letters[0], 400, rng))
    assert with_focus / 400 > 0.4
    assert plain > 0


def test_first_lesson_is_words_not_gibberish():
    """A-16: на первой ступени были наборы вроде «аопр» — теперь слоги языка."""
    letters = letter_order("ru")[:START_LETTERS]
    words = course_words("ru", letters, letters[-1], 300, random.Random(2))
    vowels = set("оеаиуыэюя")
    assert all(set(w) & vowels for w in words), "слово без гласных — не слово"


def test_text_source_uses_the_course_in_lesson_mode():
    source = TextSource("ru", Mode.LESSON, rng=random.Random(3), letters="оеаитнс", focus="с")
    phrase = source.phrase(30)
    assert set(phrase.replace(" ", "")) - {"ё"} <= set("оеаитнс")
    assert "с" in phrase
