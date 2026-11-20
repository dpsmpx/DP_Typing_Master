"""Offline achievements; no network, timers or mutable global state."""

from __future__ import annotations

from .course import START_LETTERS

MILESTONES = {
    "first": "Первый завершённый тест",
    "ten": "10 тренировок",
    "hundred": "100 тренировок",
    "thousand": "1000 тренировок",
    "combo50": "Комбо 50",
    "combo100": "Комбо 100",
    "precision": "Точность не ниже 98%",
}


def earned(tests: int, best_combo: int, accuracy: float) -> set[str]:
    result = set()
    for key, minimum in (("first", 1), ("ten", 10),
                         ("hundred", 100), ("thousand", 1000)):
        if tests >= minimum:
            result.add(key)
    if best_combo >= 50:
        result.add("combo50")
    if best_combo >= 100:
        result.add("combo100")
    if tests and accuracy >= 98:
        result.add("precision")
    return result


def stars(unlocked: int) -> int:
    """One star for each unlocked course letter after the initial six."""
    return max(0, unlocked - START_LETTERS)
