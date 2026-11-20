"""History and migration tests use an isolated on-disk SQLite database."""

from datetime import datetime, timedelta

from dp_typing.engine import Profile, TypingSession
from dp_typing.progress import daily, daily_goal, legacy_baseline, migrate_legacy, recent, record


def completed(text: str = "hello"):
    s = TypingSession(text)
    for c in text:
        s.type_char(c)
    return s.metrics()


def test_migration_keeps_aggregates_without_inventing_history(tmp_path):
    path = tmp_path / "history.sqlite3"
    p = Profile()
    p.tests, p.total_keystrokes, p.total_errors = 42, 800, 11
    assert migrate_legacy(p, path)
    p.tests = 43
    assert migrate_legacy(p, path)
    assert legacy_baseline(path)["tests"] == 42
    assert recent(path=path) == []


def test_completed_tests_record_and_group_by_local_day(tmp_path):
    path = tmp_path / "history.sqlite3"
    m = completed()
    today = datetime(2026, 11, 20, 12, 0, 0)
    assert record("ru", "common", m, path, today)
    assert record("en", "lesson", m, path, today)
    assert recent(path=path)[0]["lang"] == "en"
    result = daily(path=path)
    assert len(result) == 1
    assert result[0]["day"] == "2026-11-20"
    assert result[0]["tests"] == 2
    assert result[0]["accuracy"] == 100.0


def test_daily_goal_and_streak(tmp_path):
    path = tmp_path / "history.sqlite3"
    date = datetime(2026, 11, 20, 12, 0, 0)
    m = completed()
    for offset, times in ((0, 5), (1, 2), (2, 1), (4, 1)):
        for _ in range(times):
            assert record("ru", "common", m, path, date - timedelta(days=offset))
    assert daily_goal("2026-11-20", path=path) == {
        "done": 5, "goal": 5, "met": True, "streak": 3,
    }


def test_unwritable_history_is_nonfatal(tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    path = blocker / "history.sqlite3"
    assert not record("ru", "common", completed(), path)
    assert daily(path=path) == []
    assert not migrate_legacy(Profile(), path)
