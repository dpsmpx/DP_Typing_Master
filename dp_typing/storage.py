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
#: Версия формата. 2 — рекорды по режимам и статистика клавиш (2.2.0).
SCHEMA = 2
#: Старые версии, которые умеем перенести, а не выбросить.
READABLE_SCHEMAS = (1, 2)
#: Ключ, под которым живёт общий рекорд из профиля версии 1: в каком режиме
#: он поставлен, неизвестно, поэтому он сохраняется, но не показывается.
LEGACY_RECORD = "legacy"


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
    if not isinstance(data, dict) or data.get("schema") not in READABLE_SCHEMAS:
        return {}
    return _migrate(data)


def _migrate(data: dict) -> dict:
    """Привести профиль старой версии к текущей, ничего не потеряв."""
    if data.get("schema") == 1:
        data = dict(data)
        best = data.pop("best_wpm", None)
        if isinstance(best, (int, float)) and best > 0:
            data["records"] = {LEGACY_RECORD: float(best)}
        data["schema"] = SCHEMA
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
        "records": {k: round(v, 2) for k, v in profile.records.items()},
        "char_total": dict(profile.char_total),
        "char_errors": dict(profile.char_errors),
        "key_speed": {k: round(v, 1) for k, v in profile.key_speed.items()},
        "key_acc": {k: round(v, 4) for k, v in profile.key_acc.items()},
        "key_samples": dict(profile.key_samples),
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
    for field, target in (("char_total", profile.char_total),
                          ("char_errors", profile.char_errors),
                          ("key_samples", profile.key_samples)):
        target.update(_per_char(data.get(field), int))
    profile.key_speed.update(_per_char(data.get("key_speed"), float))
    profile.key_acc.update(_per_char(data.get("key_acc"), float))
    records = data.get("records")
    if isinstance(records, dict):
        profile.records.update(
            {k: float(v) for k, v in records.items()
             if isinstance(k, str) and _is_number(v) and v >= 0}
        )


def _is_number(value) -> bool:
    # bool — подкласс int, но True вместо числа — это мусор, а не 1.
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _per_char(raw, kind) -> dict:
    """Словарь «символ → число» из сохранённых данных; мусор отбрасывается."""
    if not isinstance(raw, dict):
        return {}
    allowed = (int,) if kind is int else (int, float)
    return {k: kind(v) for k, v in raw.items()
            if isinstance(k, str) and len(k) == 1
            and isinstance(v, allowed) and not isinstance(v, bool)}
