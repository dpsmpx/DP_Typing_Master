"""Тесты раскладок и распределения по пальцам."""

import pytest

from dp_typing.layout import (
    CAPS_LOCK,
    CAPS_LOCK_MASK,
    FINGER_NAMES,
    FINGERS,
    LAYOUTS,
    LEFT_INDEX,
    LEFT_PINKY,
    RIGHT_INDEX,
    THUMB,
    WRONG_LAYOUT,
    alphabet_of,
    finger_for,
    input_problem,
    key_zone,
)


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_rows_do_not_overlap(lang):
    layout = LAYOUTS[lang]
    letters = layout.letters
    assert len(letters) == len(set(letters)), "клавиша продублирована в двух рядах"


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_every_key_has_a_finger(lang):
    layout = LAYOUTS[lang]
    assert all(finger_for(lang, ch) is not None for ch in layout.letters)
    assert finger_for(lang, " ") == THUMB


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_anchor_keys_belong_to_index_fingers(lang):
    """Якоря слепого набора (А/О и F/J) — под указательными пальцами."""
    left, right = LAYOUTS[lang].anchors
    assert finger_for(lang, left) == LEFT_INDEX
    assert finger_for(lang, right) == RIGHT_INDEX


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_fingers_are_within_range(lang):
    assert all(0 <= f < len(FINGER_NAMES) for f in FINGERS[lang].values())


def test_finger_lookup_is_case_insensitive():
    assert finger_for("en", "F") == finger_for("en", "f")


def test_unknown_symbols_have_no_finger():
    assert finger_for("en", "§") is None
    assert finger_for("xx", "a") is None


def test_key_zone_filters_to_layout():
    assert key_zone("en", "asdf!!") == set("asdf")
    assert key_zone("xx", "asdf") == set()


# --------------------------------------------------------------------- ё

def test_yo_key_is_on_the_keyboard_with_a_finger():
    ru = LAYOUTS["ru"]
    assert ru.display_rows[0].startswith("ё")
    assert "ё" not in ru.top                  # верхний ряд уроков не меняется
    assert finger_for("ru", "ё") == LEFT_PINKY
    assert finger_for("ru", "Ё") == LEFT_PINKY


# ------------------------------------------------- раскладка ОС и Caps Lock

def test_alphabet_detection():
    assert alphabet_of("g") == alphabet_of("G") == "en"
    assert alphabet_of("п") == alphabet_of("Ё") == "ru"
    assert alphabet_of(".") is None
    assert alphabet_of("1") is None


def test_wrong_system_layout_is_recognised():
    """«ghbdtn» вместо «привет» — включена английская раскладка."""
    assert input_problem("ru", "g", "п") == WRONG_LAYOUT
    assert input_problem("en", "п", "g") == WRONG_LAYOUT


def test_caps_lock_is_recognised():
    assert input_problem("ru", "П", "п") == CAPS_LOCK                    # по регистру
    assert input_problem("ru", "К", "п", CAPS_LOCK_MASK) == CAPS_LOCK    # по биту
    assert input_problem("en", "G", "g") == CAPS_LOCK


def test_ordinary_typos_are_not_blamed_on_the_system():
    assert input_problem("ru", "к", "п") is None
    assert input_problem("ru", "п", "п") is None
    assert input_problem("ru", "п", "п", CAPS_LOCK_MASK) is None   # Caps+Shift
    assert input_problem("ru", ".", "п") is None
    assert input_problem("ru", " ", "п") is None
