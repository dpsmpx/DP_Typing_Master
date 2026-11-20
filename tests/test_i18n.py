"""English UI strings must not affect exercise text."""

from dp_typing.i18n import translate


def test_english_labels_and_russian_default():
    assert translate("СЛОВ/МИН", "en") == "WPM"
    assert translate("ПРОГРЕСС", "en") == "PROGRESS"
    assert translate("КУРС", "en") == "COURSE"
    assert translate("СЛОВ/МИН", "ru") == "СЛОВ/МИН"
