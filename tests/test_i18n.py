"""English UI strings must not affect exercise text."""

from dp_typing.i18n import translate


def test_english_labels_and_russian_default():
    assert translate("СЛОВ/МИН", "en") == "WPM"
    assert translate("ПРОГРЕСС", "en") == "PROGRESS"
    assert translate("КУРС", "en") == "COURSE"
    assert translate("СЛОВ/МИН", "ru") == "СЛОВ/МИН"


def test_english_extended_interface_labels():
    cases = {
        ("Зелёный — точно, жёлтый — 5%+ ошибок, красный — 20%+; "
         "серый — мало данных. Наведите на клавишу."): (
            "Green: accurate; yellow: 5%+ errors; red: 20%+; "
            "gray: too little data. Hover over a key."
        ),
        "Скорость (до 100)": "Speed (up to 100)",
        "Курс: ★ 7": "Course: ★ 7",
        "правый мизинец + Shift левой рукой": "right pinky + Shift with left hand",
        "Открыть следующую букву  (F4)": "Unlock next letter  (F4)",
        "ПРОБЕЛ": "SPACE",
    }
    for source, expected in cases.items():
        assert translate(source, "en") == expected
