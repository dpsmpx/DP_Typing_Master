"""Light theme stays reversible and readable without installing packages."""

from dp_typing import theme


def test_palettes_are_distinct_and_switch_back_without_leaks():
    initial = theme.BG
    try:
        theme.activate(True)
        assert theme.BG != initial
        assert theme.TEXT != theme.BG
        assert len(theme.FINGER_ZONE_COLORS) == 9
    finally:
        theme.activate(False)
    assert theme.BG == initial
