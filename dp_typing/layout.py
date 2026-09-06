"""Описание раскладок: ряды, пальцы, зоны для тренировочных уроков.

Нужно для двух вещей: экранной клавиатуры-подсказки и уроков по рядам.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Палец, которым по классике жанра бьют по клавише.
LEFT_PINKY, LEFT_RING, LEFT_MIDDLE, LEFT_INDEX = 0, 1, 2, 3
RIGHT_INDEX, RIGHT_MIDDLE, RIGHT_RING, RIGHT_PINKY = 4, 5, 6, 7
THUMB = 8

FINGER_NAMES = (
    "левый мизинец", "левый безымянный", "левый средний", "левый указательный",
    "правый указательный", "правый средний", "правый безымянный", "правый мизинец",
    "большой",
)


@dataclass(frozen=True)
class Layout:
    """Физическая раскладка: три буквенных ряда + пробел."""

    code: str
    title: str
    top: str
    home: str
    bottom: str
    #: Клавиши под указательными пальцами — «якоря» слепого набора.
    anchors: tuple[str, str]

    @property
    def rows(self) -> tuple[str, str, str]:
        return (self.top, self.home, self.bottom)

    @property
    def letters(self) -> str:
        return self.top + self.home + self.bottom


QWERTY = Layout(
    code="en",
    title="QWERTY",
    top="qwertyuiop",
    home="asdfghjkl;",
    bottom="zxcvbnm,.",
    anchors=("f", "j"),
)

JCUKEN = Layout(
    code="ru",
    title="ЙЦУКЕН",
    top="йцукенгшщзхъ",
    home="фывапролджэ",
    bottom="ячсмитьбю.",
    anchors=("а", "о"),
)

LAYOUTS: dict[str, Layout] = {"en": QWERTY, "ru": JCUKEN}


def _finger_map(layout: Layout) -> dict[str, int]:
    """Сопоставить каждой клавише палец.

    Раскладка пальцев одинакова для обеих раскладок: по два столбца на
    указательные пальцы, по одному на средний/безымянный, остальное — мизинцам.
    """
    fingers = (LEFT_PINKY, LEFT_RING, LEFT_MIDDLE, LEFT_INDEX, LEFT_INDEX,
               RIGHT_INDEX, RIGHT_INDEX, RIGHT_MIDDLE, RIGHT_RING, RIGHT_PINKY)
    out: dict[str, int] = {" ": THUMB}
    for row in layout.rows:
        for i, ch in enumerate(row):
            # Всё, что не влезло в 10 колонок (ъ, э, лишние знаки), — мизинцу.
            out[ch] = fingers[i] if i < len(fingers) else RIGHT_PINKY
    return out


FINGERS: dict[str, dict[str, int]] = {
    code: _finger_map(layout) for code, layout in LAYOUTS.items()
}


def finger_for(lang: str, ch: str) -> int | None:
    """Каким пальцем бить по символу ``ch``. ``None`` — символа нет в раскладке."""
    return FINGERS.get(lang, {}).get(ch.lower())


def key_zone(lang: str, keys: str) -> set[str]:
    """Множество символов зоны — с учётом регистра не работаем, только строчные."""
    layout = LAYOUTS.get(lang)
    if layout is None:
        return set()
    return {ch for ch in keys.lower() if ch in layout.letters}
