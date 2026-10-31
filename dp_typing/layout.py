"""Описание раскладок: ряды, пальцы, Shift, зоны для тренировочных уроков.

Нужно для двух вещей: экранной клавиатуры-подсказки и уроков по рядам.
Русская раскладка — стандартная «Русская» Windows и «Русская — ПК» macOS:
запятая там на Shift+точке, а «№», «;», «:» и «?» — в ряду цифр.
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
    #: Полная клавиатура: ряд цифр и три буквенных ряда со всеми знаками —
    #: пары «без Shift / с Shift», по позициям. Нужна для заглавных,
    #: пунктуации и цифр.
    full: tuple[tuple[str, str], ...] = ()

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
    full=(
        ("`1234567890-=", "~!@#$%^&*()_+"),
        ("qwertyuiop[]\\", "QWERTYUIOP{}|"),
        ("asdfghjkl;'", 'ASDFGHJKL:"'),
        ("zxcvbnm,./", "ZXCVBNM<>?"),
    ),
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
    full=(
        ("ё1234567890-=", 'Ё!"№;%:?*()_+'),
        ("йцукенгшщзхъ\\", "ЙЦУКЕНГШЩЗХЪ/"),
        ("фывапролджэ", "ФЫВАПРОЛДЖЭ"),
        ("ячсмитьбю.", "ЯЧСМИТЬБЮ,"),
    ),
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
    stroke = KEYMAPS.get(lang, {}).get(ch)
    if stroke is not None:
        return stroke.finger
    return FINGERS.get(lang, {}).get(ch.lower())


# ------------------------------------------------------ полная клавиатура

#: Пальцы по колонкам буквенных рядов (сверх десяти колонок — мизинец).
_COLUMN_FINGERS = (LEFT_PINKY, LEFT_RING, LEFT_MIDDLE, LEFT_INDEX, LEFT_INDEX,
                   RIGHT_INDEX, RIGHT_INDEX, RIGHT_MIDDLE, RIGHT_RING, RIGHT_PINKY)


@dataclass(frozen=True)
class Stroke:
    """Как набрать символ: какая клавиша, нужен ли Shift и каким пальцем."""

    key: str          # символ клавиши без Shift — её имя на экранной клавиатуре
    shift: bool
    finger: int

    @property
    def left_hand(self) -> bool:
        return self.finger <= LEFT_INDEX

    @property
    def shift_side(self) -> str | None:
        """Какой Shift жать: противоположной рукой, как учат при слепом наборе."""
        if not self.shift:
            return None
        return "right" if self.left_hand else "left"


def _stroke_finger(row: int, col: int) -> int:
    if row == 0:
        # Ряд цифр сдвинут на колонку влево: «ё»/«`» и «1» — левый мизинец,
        # дальше 2 — безымянный, 3 — средний, 4-5 — указательный и т.д.
        col -= 1
        if col < 0:
            return LEFT_PINKY
    return _COLUMN_FINGERS[col] if col < len(_COLUMN_FINGERS) else RIGHT_PINKY


def _keymap(layout: Layout) -> dict[str, Stroke]:
    out: dict[str, Stroke] = {" ": Stroke(" ", False, THUMB)}
    for row, (plain, shifted) in enumerate(layout.full):
        for col, (base, upper) in enumerate(zip(plain, shifted)):
            finger = _stroke_finger(row, col)
            out.setdefault(base, Stroke(base, False, finger))
            out.setdefault(upper, Stroke(base, True, finger))
    return out


#: Символ → как его набрать, для каждой раскладки.
KEYMAPS: dict[str, dict[str, Stroke]] = {
    code: _keymap(layout) for code, layout in LAYOUTS.items()
}


def stroke_for(lang: str, ch: str) -> Stroke | None:
    """Как набрать ``ch`` в раскладке ``lang``; None — такого символа на ней нет."""
    return KEYMAPS.get(lang, {}).get(ch)


def key_zone(lang: str, keys: str) -> set[str]:
    """Множество символов зоны — с учётом регистра не работаем, только строчные."""
    layout = LAYOUTS.get(lang)
    if layout is None:
        return set()
    return {ch for ch in keys.lower() if ch in layout.letters}


# ------------------------------------------------- проблемы ввода

#: Биты ``event.state`` Tk — одинаковы на X11, Windows и macOS.
SHIFT_MASK = 0x1
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
    # Бит Lock надёжен не везде, поэтому есть и запасной признак: заглавная
    # пришла без зажатого Shift. Если Shift зажат, заглавная — просто ошибка
    # пальцев, Caps Lock тут ни при чём.
    locked = bool(state & CAPS_LOCK_MASK) or (ch.isupper() and not state & SHIFT_MASK)
    if locked and ch.isalpha() and ch != expected:
        return CAPS_LOCK
    return None
