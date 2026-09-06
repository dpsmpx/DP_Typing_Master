"""Тесты источников текста."""

import random

import pytest

from dp_typing.words import (
    MAX_WORD_LEN,
    MIN_WORD_LEN,
    Mode,
    TextSource,
    adaptive_weights,
    lesson_stages,
    load_words,
    pseudo_word,
    words_for_zone,
)

RU_ALPHABET = set("абвгдеёжзийклмнопрстуфхцчшщъыьэюя")
EN_ALPHABET = set("abcdefghijklmnopqrstuvwxyz")


@pytest.fixture
def rng():
    return random.Random(1234)


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_wordlist_loads_and_is_clean(lang):
    words = load_words(lang)
    assert len(words) > 1000
    assert all(MIN_WORD_LEN <= len(w) <= MAX_WORD_LEN for w in words)
    assert all(w == w.strip().lower() for w in words)
    assert len(set(words)) == len(words), "в словаре есть дубликаты"


@pytest.mark.parametrize("lang,alphabet", [("ru", RU_ALPHABET), ("en", EN_ALPHABET)])
def test_wordlist_covers_whole_alphabet(lang, alphabet):
    """Ревью #8: буква «й» раньше не генерировалась вообще."""
    assert alphabet <= set("".join(load_words(lang)))


def test_unknown_language_rejected():
    with pytest.raises(ValueError):
        load_words("de")


# ------------------------------------------------------------- псевдослова

@pytest.mark.parametrize("lang,alphabet", [("ru", RU_ALPHABET), ("en", EN_ALPHABET)])
def test_pseudo_words_are_well_formed(lang, alphabet, rng):
    for _ in range(500):
        w = pseudo_word(lang, rng)
        assert MIN_WORD_LEN <= len(w) <= MAX_WORD_LEN
        assert set(w) <= alphabet, f"посторонний символ в {w!r}"


def test_pseudo_words_are_mostly_novel(rng):
    """Генератор должен придумывать слова, а не пересказывать словарь."""
    real = set(load_words("ru"))
    made = [pseudo_word("ru", rng) for _ in range(400)]
    novel = sum(1 for w in made if w not in real)
    assert novel / len(made) > 0.5


def test_pseudo_generation_is_reproducible():
    a = [pseudo_word("en", random.Random(7)) for _ in range(5)]
    b = [pseudo_word("en", random.Random(7)) for _ in range(5)]
    assert a == b


# ------------------------------------------------------------------- уроки

@pytest.mark.parametrize("lang", ["ru", "en"])
def test_lesson_stages_widen_monotonically(lang):
    stages = lesson_stages(lang)
    assert len(stages) >= 4
    sizes = [len(set(keys)) for _, keys in stages]
    assert sizes == sorted(sizes), "ступени должны расширяться, а не сужаться"


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_lesson_phrase_stays_inside_its_zone(lang, rng):
    """Урок не имеет права подсунуть клавишу, которую ещё не проходили."""
    for stage, (_title, keys) in enumerate(lesson_stages(lang)):
        source = TextSource(lang, Mode.LESSON, stage=stage, rng=rng)
        used = set(source.phrase(40).replace(" ", ""))
        assert used <= set(keys), f"ступень {stage}: лишние клавиши {used - set(keys)}"


def test_zone_words_are_filtered_correctly():
    pool = words_for_zone("ru", "фывапролдж")
    assert pool, "домашний ряд обязан давать хоть какие-то слова"
    assert all(set(w) <= set("фывапролдж") for w in pool)


def test_narrow_zone_falls_back_to_synthetic(rng):
    """Для «fghj» реальных английских слов нет — нужен запасной генератор."""
    assert words_for_zone("en", "fghj") == ()
    phrase = TextSource("en", Mode.LESSON, stage=0, rng=rng).phrase(6)
    assert phrase and set(phrase.replace(" ", "")) <= set("fghj")


# ---------------------------------------------------------------- адаптив

def test_adaptive_weights_favour_weak_letters():
    words = ["aaa", "zzz", "azz"]
    weights = adaptive_weights(words, [("z", 0.5)], boost=6.0)
    assert weights[0] == 1.0
    assert weights[1] == pytest.approx(4.0)
    assert weights[2] == pytest.approx(4.0)


def test_adaptive_weights_neutral_without_history():
    words = ["aaa", "zzz"]
    assert adaptive_weights(words, []) == [1.0, 1.0]


def test_adaptive_mode_actually_shifts_the_distribution():
    weak = [("ц", 0.6), ("щ", 0.5)]
    plain = TextSource("ru", Mode.COMMON, rng=random.Random(3)).phrase(3000).split()
    tuned = TextSource("ru", Mode.ADAPTIVE, rng=random.Random(3)).phrase(3000, weak).split()

    def share(words):
        return sum(1 for w in words if set(w) & set("цщ")) / len(words)

    assert share(tuned) > share(plain) * 2, "адаптив должен заметно чаще давать слабые буквы"


# ------------------------------------------------------------------- фраза

@pytest.mark.parametrize("mode", list(Mode))
@pytest.mark.parametrize("lang", ["ru", "en"])
def test_every_mode_produces_a_usable_phrase(mode, lang, rng):
    phrase = TextSource(lang, mode, rng=rng).phrase(9)
    assert phrase.strip()
    assert len(phrase.split()) == 9
    assert "  " not in phrase
    assert phrase == phrase.strip()


# --------------------------------------------------------- гигиена словарей

#: Проверочная выборка: если хоть одно из этих слов вернулось в словарь,
#: значит фильтр при пересборке списков сломался.
PROFANITY = {
    "ru": {"дерьмо", "говно", "жопа", "сука", "блядь", "хуй", "мудак", "срать",
           "ублюдок", "тварь", "идиот", "убить", "труп"},
    "en": {"shit", "fuck", "bitch", "damn", "hell", "ass", "crap", "bastard",
           "stupid", "idiot", "kill", "murder", "dead"},
}


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_wordlist_has_no_profanity(lang):
    found = PROFANITY[lang] & set(load_words(lang))
    assert not found, f"в словаре {lang} появилась брань: {sorted(found)}"


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_generated_phrases_stay_clean(lang, rng):
    """Псевдослова строятся на словаре, но проверим и их выдачу."""
    words = set(TextSource(lang, Mode.COMMON, rng=rng).phrase(2000).split())
    assert not (PROFANITY[lang] & words)
