"""Сохранение профиля между запусками.

Файл лежит в пользовательском конфиг-каталоге. Любая ошибка ввода-вывода
проглатывается: тренажёр обязан работать и без права на запись.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from .engine import Profile

APP_DIR = "dp-typing-master"
FILE_NAME = "profile.json"
SCHEMA = 1


def config_path() -> Path:
    """Путь к файлу профиля по конвенциям платформы."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / APP_DIR / FILE_NAME


def load(path: Path | None = None) -> dict:
    path = path or config_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        return {}
    return data


def save(profile: Profile, extra: dict | None = None, path: Path | None = None) -> bool:
    """Записать профиль. Возвращает True, если получилось."""
    path = path or config_path()
    payload = {
        "schema": SCHEMA,
        "tests": profile.tests,
        "total_keystrokes": profile.total_keystrokes,
        "total_errors": profile.total_errors,
        "total_time": round(profile.total_time, 2),
        "best_combo": profile.best_combo,
        "best_wpm": round(profile.best_wpm, 2),
        "char_total": dict(profile.char_total),
        "char_errors": dict(profile.char_errors),
        **(extra or {}),
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)  # атомарная замена — файл не бьётся при сбое
        return True
    except OSError:
        return False


def restore(profile: Profile, data: dict) -> None:
    """Влить сохранённые данные в профиль (значения проверяются на тип)."""
    def _num(key: str, default=0):
        value = data.get(key, default)
        return value if isinstance(value, (int, float)) else default

    profile.tests = int(_num("tests"))
    profile.total_keystrokes = int(_num("total_keystrokes"))
    profile.total_errors = int(_num("total_errors"))
    profile.total_time = float(_num("total_time", 0.0))
    profile.best_combo = int(_num("best_combo"))
    profile.best_wpm = float(_num("best_wpm", 0.0))
    for field, target in (("char_total", profile.char_total),
                          ("char_errors", profile.char_errors)):
        raw = data.get(field)
        if isinstance(raw, dict):
            target.update(
                {k: int(v) for k, v in raw.items()
                 if isinstance(k, str) and len(k) == 1 and isinstance(v, int)}
            )
