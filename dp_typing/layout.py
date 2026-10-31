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
    #: Буквы из ряда цифр (ё в ЙЦУКЕН). На экранной клавиатуре рисуются
    #: слева от верхнего ряда, бьются левым мизинцем.
    top_extra: str = ""
    #: Название раскладки в родительном/винительном падеже для подсказок:
    #: «переключите на русскую».
    accusative: str = ""

    @property
    def rows(self) -> tuple[str, str, str]:
        return (self.top, self.home, self.bottom)

    @property
    def display_rows(self) -> tuple[str, str, str]:
        """Ряды так, как они рисуются на экранной клавиатуре."""
        return (self.top_extra + self.top, self.home, self.bottom)

    @property
    def letters(self) -> str:
        return self.top_extra + self.top + self.home + self.bottom


QWERTY = Layout(
    code="en",
    title="QWERTY",
    top="qwertyuiop",
    home="asdfghjkl;",
    bottom="zxcvbnm,.",
    anchors=("f", "j"),
    accusative="английскую",
)

JCUKEN = Layout(
    code="ru",
    title="ЙЦУКЕН",
    top="йцукенгшщзхъ",
    home="фывапролджэ",
    bottom="ячсмитьбю.",
    anchors=("а", "о"),
    top_extra="ё",
    accusative="русскую",
)

LAYOUTS: dict[str, Layout] = {"en": QWERTY, "ru": JCUKEN}

#: Какие нажатия засчитываются вместо символа цели. «Ё» в русских текстах
#: пишут через раз, а на многих клавиатурах она в неудобном углу, поэтому
#: «е» на месте «ё» — не ошибка.
EQUIVALENTS: dict[str, dict[str, str]] = {
    "ru": {"ё": "е", "Ё": "Е"},
    "en": {},
}


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
    for ch in layout.top_extra:
        out[ch] = LEFT_PINKY
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


# ------------------------------------------------- проблемы ввода

#: Бит Caps Lock в ``event.state`` Tk (LockMask) — одинаков на X11, Windows
#: и macOS.
CAPS_LOCK_MASK = 0x2

#: Проблемы, о которых стоит предупредить: нажатие пришло «не туда» по вине
#: системной раскладки или Caps Lock, а не пальцев.
WRONG_LAYOUT = "layout"
CAPS_LOCK = "caps"


def alphabet_of(ch: str) -> str | None:
    """Код раскладки, которой принадлежит буква, или None для прочих символов."""
    if "a" <= ch.lower() <= "z":
        return "en"
    if "\u0400" <= ch <= "\u04ff":
        return "ru"
    return None


def input_problem(lang: str, ch: str, expected: str, state: int = 0) -> str | None:
    """Распознать нажатие, испорченное системной раскладкой или Caps Lock.

    ``expected`` — символ, который ожидался на этой позиции. Возвращает
    ``WRONG_LAYOUT``, ``CAPS_LOCK`` или None, если всё в порядке.
    """
    script = alphabet_of(ch)
    if script is not None and script != lang and alphabet_of(expected) != script:
        return WRONG_LAYOUT
    # Бит Lock надёжен не везде, поэтому есть и запасной признак: набрана
    # заглавная там, где ждали ту же строчную.
    caps = state & CAPS_LOCK_MASK or (ch.isupper() and ch.lower() == expected)
    if ch.isalpha() and ch != expected and caps:
        return CAPS_LOCK
    return None
