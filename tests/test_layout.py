"""Тесты раскладок и распределения по пальцам."""

import pytest

from dp_typing.layout import (
    CAPS_LOCK,
    CAPS_LOCK_MASK,
    FINGER_NAMES,
    FINGERS,
    KEYMAPS,
    LAYOUTS,
    LEFT_INDEX,
    LEFT_PINKY,
    LEFT_RING,
    RIGHT_INDEX,
    RIGHT_PINKY,
    SHIFT_MASK,
    THUMB,
    WRONG_LAYOUT,
    alphabet_of,
    finger_for,
    input_problem,
    key_zone,
    stroke_for,
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


# ------------------------------------------------- полная клавиатура и Shift


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_full_rows_pair_up(lang):
    for plain, shifted in LAYOUTS[lang].full:
        assert len(plain) == len(shifted)


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_every_letter_and_its_capital_are_typeable(lang):
    for ch in LAYOUTS[lang].letters:
        assert stroke_for(lang, ch) is not None, ch
        if ch.isalpha():
            upper = stroke_for(lang, ch.upper())
            assert upper.shift and upper.key == ch
            assert upper.finger == stroke_for(lang, ch).finger


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_punctuation_and_digits_are_typeable(lang):
    for ch in ".,!?:;-()\"0123456789":
        assert stroke_for(lang, ch) is not None, f"{lang}: нет «{ch}»"


def test_russian_punctuation_positions():
    """ЙЦУКЕН: запятая — Shift+точка, «?» — Shift+7, «№» — Shift+3."""
    comma = stroke_for("ru", ",")
    assert comma.key == "." and comma.shift
    assert stroke_for("ru", "?").key == "7"
    assert stroke_for("ru", "№").key == "3"
    assert stroke_for("ru", "Ё").key == "ё"


def test_number_row_fingers():
    assert finger_for("en", "1") == LEFT_PINKY
    assert finger_for("en", "2") == LEFT_RING
    assert finger_for("en", "5") == LEFT_INDEX
    assert finger_for("en", "6") == RIGHT_INDEX
    assert finger_for("en", "0") == RIGHT_PINKY
    assert finger_for("ru", "!") == LEFT_PINKY
    assert finger_for("ru", "@") is None


def test_shift_is_pressed_by_the_other_hand():
    assert stroke_for("en", "A").shift_side == "right"     # a — левая рука
    assert stroke_for("en", "P").shift_side == "left"      # p — правая
    assert stroke_for("ru", ",").shift_side == "left"      # точка — правый мизинец
    assert stroke_for("ru", "а").shift_side is None


def test_letter_fingers_match_lesson_map():
    """Новая карта и старая (по рядам уроков) согласны по всем буквам."""
    for lang, layout in LAYOUTS.items():
        for ch in layout.letters:
            assert KEYMAPS[lang][ch].finger == FINGERS[lang][ch], (lang, ch)
    assert finger_for("ru", "ъ") == RIGHT_PINKY
    assert finger_for("en", "q") == LEFT_PINKY
    assert finger_for("ru", "ц") == LEFT_RING


def test_capital_with_shift_held_is_not_caps_lock():
    """С текстом, где есть заглавные, Shift не путается с Caps Lock."""
    assert input_problem("ru", "П", "п", SHIFT_MASK) is None
    assert input_problem("ru", "п", "П", CAPS_LOCK_MASK | SHIFT_MASK) == CAPS_LOCK
    assert input_problem("ru", "П", "П", CAPS_LOCK_MASK) is None
