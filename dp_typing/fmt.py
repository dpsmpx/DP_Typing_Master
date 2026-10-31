"""Форматирование текста для интерфейса: склонения и перенос фразы.

Без tkinter — проверяется headless.
"""

from __future__ import annotations

from typing import Callable


def plural(n: int, one: str, few: str, many: str) -> str:
    """Форма слова для числа по правилам русского языка.

    >>> plural(1, "тест", "теста", "тестов"), plural(3, "тест", "теста", "тестов")
    ('тест', 'теста')
    >>> plural(11, "тест", "теста", "тестов"), plural(21, "тест", "теста", "тестов")
    ('тестов', 'тест')
    """
    n = abs(n)
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def count(n: int, one: str, few: str, many: str) -> str:
    """Число вместе со словом: «4 теста», «11 ошибок»."""
    return f"{n} {plural(n, one, few, many)}"


def wrap_words(text: str, width: float, measure: Callable[[str], float]) -> list[str]:
    """Разбить фразу на строки шириной не больше ``width`` по словам.

    Пробел на месте переноса остаётся в конце строки — его тоже нужно
    напечатать, поэтому ``"".join(result) == text`` всегда. Слово длиннее
    строки не режется, а занимает строку целиком.

    Перенос делается вручную, а не средствами ``tk.Text``: тогда каждую строку
    можно центрировать отступом при выравнивании влево. При ``justify=center``
    Tk растягивает фон первого символа строки до левого края, и каретка в
    начале строки превращалась в полосу.
    """
    if width <= 0:
        return [text]
    words = text.split(" ")
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if measure(candidate) > width:
            lines.append(current + " ")
            current = word
        else:
            current = candidate
    lines.append(current)
    return lines
