"""Тесты сохранения профиля. Ни один сбой ввода-вывода не должен ронять приложение."""

import json

from dp_typing.engine import Profile
from dp_typing.storage import LEGACY_RECORD, SCHEMA, config_path, load, restore, save


def make_profile() -> Profile:
    p = Profile()
    p.tests = 4
    p.total_keystrokes = 400
    p.total_errors = 12
    p.total_time = 95.5
    p.best_combo = 61
    p.records["ru/common/phrase"] = 58.25
    p.char_total.update({"а": 40, "б": 12})
    p.char_errors.update({"б": 5})
    p.key_speed.update({"а": 210.5, "б": 120.0})
    p.key_acc.update({"а": 0.99, "б": 0.6})
    p.key_samples.update({"а": 40, "б": 12})
    return p


def test_round_trip(tmp_path):
    path = tmp_path / "profile.json"
    assert save(make_profile(), {"lang": "en"}, path=path) is True

    restored = Profile()
    restore(restored, load(path))
    assert restored.tests == 4
    assert restored.total_keystrokes == 400
    assert restored.best_combo == 61
    assert restored.record("ru/common/phrase") == 58.25
    assert restored.char_errors["б"] == 5
    assert restored.key_speed["а"] == 210.5
    assert restored.key_acc["б"] == 0.6
    assert restored.key_samples["б"] == 12
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
    restore(p, {"tests": "много", "records": {"x": "быстро", "y": -3, "z": True, "ok": 40},
                "char_total": "нет", "char_errors": {"аб": 3, "в": "пять", "г": 2},
                "key_speed": {"а": "быстро", "б": 150}, "key_acc": [1, 2]})
    assert p.tests == 0
    assert p.records == {"ok": 40.0}
    assert dict(p.char_errors) == {"г": 2}   # взяли только валидную пару
    assert p.key_speed == {"б": 150.0}
    assert p.key_acc == {}


def test_version_1_profile_is_migrated_not_dropped(tmp_path):
    """Профиль из 2.0/2.1 не выбрасывается: статистика переносится, а общий
    рекорд сохраняется отдельно — в каком режиме он поставлен, неизвестно."""
    path = tmp_path / "profile.json"
    path.write_text(json.dumps({"schema": 1, "tests": 9, "best_wpm": 61.5,
                                "char_total": {"а": 3}, "lang": "en"}), encoding="utf-8")
    data = load(path)
    assert data["schema"] == SCHEMA
    assert data["lang"] == "en"
    p = Profile()
    restore(p, data)
    assert p.tests == 9
    assert p.char_total["а"] == 3
    assert p.record(LEGACY_RECORD) == 61.5


def test_unwritable_path_reports_failure(tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("я файл, а не каталог", encoding="utf-8")
    assert save(make_profile(), path=blocker / "sub" / "profile.json") is False


def test_config_path_is_absolute_and_named():
    path = config_path()
    assert path.is_absolute()
    assert path.name == "profile.json"
