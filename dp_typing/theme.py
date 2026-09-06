"""Палитра, шрифты и уровни комбо.

Цвета собраны в одном месте, чтобы UI не был усеян магическими строками,
а подбор шрифта шёл через реально доступные в системе семейства
(«Courier» на Windows не существует — там «Courier New»).
"""

from __future__ import annotations

from dataclasses import dataclass

# --------------------------------------------------------------- палитра

BG = "#0e1014"
PANEL = "#161a22"
PANEL_HI = "#1e2430"
BORDER = "#252c3a"

TEXT = "#e8ecf4"
TEXT_DIM = "#8a93a6"
TEXT_FAINT = "#4d5567"

PENDING = "#5a6478"
CORRECT = "#e8ecf4"
WRONG_FG = "#ff6b6b"
WRONG_BG = "#3a1d22"
CARET = "#4c8dff"
CARET_DIM = "#24406e"

ACCENT = "#4c8dff"
GOOD = "#3ddc97"
WARN = "#ffb454"
BAD = "#ff6b6b"

KEY_BG = "#1b2029"
KEY_FG = "#7d8698"
KEY_NEXT_BG = "#4c8dff"
KEY_NEXT_FG = "#ffffff"
KEY_HOME_BG = "#232b38"

# ------------------------------------------------------------------ комбо


@dataclass(frozen=True)
class ComboTier:
    threshold: int
    name: str
    color: str
    flash: str


#: Уровни комбо — по возрастанию порога.
COMBO_TIERS: tuple[ComboTier, ...] = (
    ComboTier(0, "", TEXT_FAINT, TEXT_DIM),
    ComboTier(10, "разогрев", "#5aa9ff", "#b9d9ff"),
    ComboTier(25, "в потоке", GOOD, "#c4ffe8"),
    ComboTier(50, "разгон", WARN, "#ffe3b8"),
    ComboTier(100, "огонь", "#ff7ab8", "#ffd6ea"),
    ComboTier(200, "легенда", "#c98bff", "#ecd8ff"),
)


def combo_tier(combo: int) -> ComboTier:
    """Уровень для текущего комбо."""
    tier = COMBO_TIERS[0]
    for candidate in COMBO_TIERS:
        if combo >= candidate.threshold:
            tier = candidate
        else:
            break
    return tier


def next_threshold(combo: int) -> int | None:
    """Порог следующего уровня — для полоски прогресса комбо."""
    for tier in COMBO_TIERS:
        if tier.threshold > combo:
            return tier.threshold
    return None


def accuracy_color(accuracy: float) -> str:
    if accuracy >= 97.0:
        return GOOD
    if accuracy >= 92.0:
        return WARN
    return BAD


# ----------------------------------------------------------------- шрифты

#: Кандидаты по убыванию предпочтения; берём первый установленный.
MONO_FAMILIES = (
    "JetBrains Mono", "Cascadia Mono", "Consolas", "DejaVu Sans Mono",
    "Liberation Mono", "Menlo", "Courier New", "TkFixedFont",
)
UI_FAMILIES = (
    "Inter", "Segoe UI", "SF Pro Text", "Ubuntu", "DejaVu Sans",
    "Liberation Sans", "Helvetica", "TkDefaultFont",
)


def pick_family(available: set[str], candidates: tuple[str, ...]) -> str:
    """Первое семейство из ``candidates``, которое есть в системе."""
    for name in candidates:
        if name in available:
            return name
    return candidates[-1]
