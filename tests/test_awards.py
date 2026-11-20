"""Deterministic achievements for offline use."""

from dp_typing.awards import earned, stars


def test_stars_follow_unlocked_course_levels():
    assert stars(6) == 0
    assert stars(11) == 5


def test_milestones():
    assert earned(0, 0, 100) == set()
    result = earned(100, 50, 98)
    assert {"first", "ten", "hundred", "combo50", "precision"} <= result
    assert "thousand" not in result
