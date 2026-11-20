"""Offline SQLite history for completed typing tests.

Dates are stored in the user's local time zone. Old JSON aggregate totals are
preserved as a *baseline*, not invented per-day historical observations.
Database failures must never prevent the typing trainer from running.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

from . import storage

GOAL_TESTS = 5


def database_path() -> Path:
    return storage.config_path().with_name("history.sqlite3")


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path), timeout=1.0)
    try:
        db.execute("""CREATE TABLE IF NOT EXISTS tests (
            id INTEGER PRIMARY KEY,
            created_at TEXT NOT NULL,
            lang TEXT NOT NULL,
            mode TEXT NOT NULL,
            wpm REAL NOT NULL CHECK(wpm >= 0),
            accuracy REAL NOT NULL CHECK(accuracy BETWEEN 0 AND 100),
            errors INTEGER NOT NULL CHECK(errors >= 0),
            keystrokes INTEGER NOT NULL CHECK(keystrokes >= 0),
            duration REAL NOT NULL CHECK(duration >= 0)
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY, value TEXT NOT NULL
        )""")
        db.execute("CREATE INDEX IF NOT EXISTS idx_tests_date ON tests(created_at)")
        db.commit()
    except sqlite3.Error:
        db.close()
        raise
    return db


def migrate_legacy(profile, path: Path | None = None) -> bool:
    """Preserve old aggregate counters once, with no fabricated dates."""
    path = path if path is not None else database_path()
    try:
        with closing(_connect(path)) as db, db:
            db.execute(
                "INSERT OR IGNORE INTO metadata(key, value) VALUES (?, ?)",
                ("legacy_baseline", json.dumps({
                    "tests": profile.tests,
                    "keystrokes": profile.total_keystrokes,
                    "errors": profile.total_errors,
                    "seconds": profile.total_time,
                })),
            )
        return True
    except (OSError, sqlite3.Error, ValueError):
        return False


def record(lang: str, mode: str, metrics, path: Path | None = None,
           when: datetime | None = None) -> bool:
    """Append one completed test; never create a fake row for an abandoned test."""
    path = path if path is not None else database_path()
    when = when if when is not None else datetime.now().astimezone()
    try:
        with closing(_connect(path)) as db, db:
            values = (when.isoformat(timespec="seconds"), lang, mode, metrics.wpm,
                      metrics.accuracy, metrics.errors, metrics.keystrokes, metrics.elapsed)
            db.execute("""INSERT INTO tests
                (created_at, lang, mode, wpm, accuracy, errors, keystrokes, duration)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", values)
        return True
    except (OSError, sqlite3.Error, ValueError, OverflowError):
        return False


def recent(limit: int = 30, path: Path | None = None) -> list[dict]:
    path = path if path is not None else database_path()
    try:
        with closing(_connect(path)) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute("""SELECT created_at, lang, mode, wpm, accuracy,
                                       errors, keystrokes, duration
                                 FROM tests ORDER BY id DESC LIMIT ?""",
                              (max(0, min(limit, 365)),)).fetchall()
        return [dict(row) for row in rows]
    except (OSError, sqlite3.Error):
        return []


def daily(limit: int = 30, path: Path | None = None) -> list[dict]:
    """Chronological daily chart data, with weighted accuracy by keystrokes."""
    path = path if path is not None else database_path()
    try:
        with closing(_connect(path)) as db:
            db.row_factory = sqlite3.Row
            sql = """SELECT substr(created_at, 1, 10) AS day,
                COUNT(*) AS tests, ROUND(AVG(wpm), 2) AS wpm,
                ROUND(100.0 * (SUM(keystrokes) - SUM(errors)) /
                    NULLIF(SUM(keystrokes), 0), 2) AS accuracy
                FROM tests GROUP BY day ORDER BY day DESC LIMIT ?"""
            rows = db.execute(sql, (max(0, min(limit, 365)),)).fetchall()
        return list(reversed([dict(row) for row in rows]))
    except (OSError, sqlite3.Error):
        return []


def daily_goal(today: str | None = None, target: int = GOAL_TESTS,
               path: Path | None = None) -> dict:
    """Completed tests today and consecutive days ending today or yesterday."""
    today = today or datetime.now().astimezone().date().isoformat()
    from datetime import date, timedelta

    totals = {row["day"]: row["tests"] for row in daily(365, path)}
    count = totals.get(today, 0)
    cursor = date.fromisoformat(today)
    if not totals.get(today):
        cursor -= timedelta(days=1)
    streak = 0
    while totals.get(cursor.isoformat(), 0) > 0:
        streak += 1
        cursor -= timedelta(days=1)
    return {"done": count, "goal": target, "met": count >= target, "streak": streak}


def legacy_baseline(path: Path | None = None) -> dict:
    path = path if path is not None else database_path()
    try:
        with closing(_connect(path)) as db:
            row = db.execute(
                "SELECT value FROM metadata WHERE key = 'legacy_baseline'"
            ).fetchone()
        return json.loads(row[0]) if row else {}
    except (OSError, sqlite3.Error, ValueError, TypeError):
        return {}


def clear_history(path: Path | None = None) -> bool:
    """F7 reset must clear history as well as the JSON profile."""
    path = path if path is not None else database_path()
    try:
        with closing(_connect(path)) as db, db:
            db.execute("DELETE FROM tests")
            db.execute("DELETE FROM metadata")
        return True
    except (OSError, sqlite3.Error):
        return False
