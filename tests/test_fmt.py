"""Склонения и перенос фразы по строкам."""

import pytest

from dp_typing.fmt import count, plural, wrap_words

FORMS = ("тест", "теста", "тестов")


@pytest.mark.parametrize(("n", "expected"), [
    (0, "тестов"), (1, "тест"), (2, "теста"), (4, "теста"), (5, "тестов"),
    (11, "тестов"), (12, "тестов"), (14, "тестов"), (21, "тест"), (22, "теста"),
    (101, "тест"), (111, "тестов"), (1000, "тестов"),
])
def test_plural_forms(n, expected):
    assert plural(n, *FORMS) == expected


def test_count_joins_number_and_word():
    assert count(2, "ошибка", "ошибки", "ошибок") == "2 ошибки"


def mono(s: str) -> float:
    """Моноширинный шрифт: 10 px на символ."""
    return 10.0 * len(s)


@pytest.mark.parametrize("text", [
    "коротко",
    "фраза подлиннее которая не влезет в одну строку",
    "а б в г д е ж з и к л м н о п р с т у ф х ц ч ш щ",
    "сверхдлинноеслово и ещё слова",
])
@pytest.mark.parametrize("width", [60, 100, 200, 1000])
def test_wrap_keeps_every_character(text, width):
    """Позиции в строках однозначно отображаются на позиции во фразе."""
    lines = wrap_words(text, width, mono)
    assert "".join(lines) == text


def test_wrap_respects_width():
    lines = wrap_words("один два три четыре пять шесть", 100, mono)
    assert all(mono(line.rstrip(" ")) <= 100 for line in lines)
    assert lines == ["один два ", "три четыре ", "пять шесть"]


def test_wrap_puts_space_at_line_end():
    lines = wrap_words("аа бб вв", 50, mono)
    assert lines == ["аа бб ", "вв"]


def test_overlong_word_takes_its_own_line():
    assert wrap_words("сверхдлинноеслово да", 50, mono) == ["сверхдлинноеслово ", "да"]


def test_unknown_width_means_single_line():
    assert wrap_words("а б в", 0, mono) == ["а б в"]
