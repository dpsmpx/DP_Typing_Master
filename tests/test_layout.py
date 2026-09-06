"""Тесты раскладок и распределения по пальцам."""

import pytest

from dp_typing.layout import (
    FINGER_NAMES,
    FINGERS,
    LAYOUTS,
    LEFT_INDEX,
    RIGHT_INDEX,
    THUMB,
    finger_for,
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
