"""Тесты сохранения профиля. Ни один сбой ввода-вывода не должен ронять приложение."""

import json

from dp_typing.engine import Profile
from dp_typing.storage import SCHEMA, config_path, load, restore, save


def make_profile() -> Profile:
    p = Profile()
    p.tests = 4
    p.total_keystrokes = 400
    p.total_errors = 12
    p.total_time = 95.5
    p.best_combo = 61
    p.best_wpm = 58.25
    p.char_total.update({"а": 40, "б": 12})
    p.char_errors.update({"б": 5})
    return p


def test_round_trip(tmp_path):
    path = tmp_path / "profile.json"
    assert save(make_profile(), {"lang": "en"}, path=path) is True

    restored = Profile()
    restore(restored, load(path))
    assert restored.tests == 4
    assert restored.total_keystrokes == 400
    assert restored.best_combo == 61
    assert restored.best_wpm == 58.25
    assert restored.char_errors["б"] == 5
    assert load(path)["lang"] == "en"


def test_missing_file_gives_empty_dict(tmp_path):
    assert load(tmp_path / "nope.json") == {}


def test_corrupt_file_is_ignored(tmp_path):
    path = tmp_path / "profile.json"
    path.write_text("{ это не json", encoding="utf-8")
    assert load(path) == {}


def test_foreign_schema_is_ignored(tmp_path):
    path = tmp_path / "profile.json"
    path.write_text(json.dumps({"schema": SCHEMA + 99, "tests": 5}), encoding="utf-8")
    assert load(path) == {}


def test_restore_survives_garbage_values():
    """Испорченный файл не должен превращаться в исключение при старте."""
    p = Profile()
    restore(p, {"tests": "много", "best_wpm": None, "char_total": "нет",
                "char_errors": {"аб": 3, "в": "пять", "г": 2}})
    assert p.tests == 0
    assert p.best_wpm == 0.0
    assert dict(p.char_errors) == {"г": 2}   # взяли только валидную пару


def test_unwritable_path_reports_failure(tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("я файл, а не каталог", encoding="utf-8")
    assert save(make_profile(), path=blocker / "sub" / "profile.json") is False


def test_config_path_is_absolute_and_named():
    path = config_path()
    assert path.is_absolute()
    assert path.name == "profile.json"
