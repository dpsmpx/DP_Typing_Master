"""Optional English user interface, independent of the keyboard language.

We translate UI labels and help, not exercise text. Keep the dictionary
centralized so that dialogs, result views and shortcuts use consistent terms.
"""

from __future__ import annotations

ENGLISH = {
    "СЛОВ/МИН": "WPM", "ЗНАКОВ/МИН": "CPM", "ТОЧНОСТЬ": "ACCURACY",
    "ОШИБКИ": "ERRORS", "РЕКОРД": "RECORD", "ОСТАЛОСЬ, С": "SECONDS LEFT",
    "СЛОВА": "WORDS", "ФРАЗА": "PHRASE", "КОМБО": "COMBO",
    "ПРОГРЕСС": "PROGRESS", "РУССКИЙ": "RUSSIAN",
    "УКРАЇНСЬКА": "UKRAINIAN", "БЕЛАРУСКАЯ": "BELARUSIAN",
    "ЧАСТОТНЫЕ СЛОВА": "COMMON WORDS", "ПСЕВДОСЛОВА": "PSEUDOWORDS",
    "СЛАБЫЕ КЛАВИШИ": "WEAK KEYS", "СВОЙ ТЕКСТ": "CUSTOM TEXT",
    "КУРС": "COURSE", "ФОКУС": "FOCUS", "ФРАЗА": "PHRASE",
    "Горячие клавиши": "Keyboard shortcuts",
    "Тренировка": "Training", "Настройки": "Settings",
    "Раскладка EN": "English keyboard", "Справка": "Help",
    "Язык": "Language", "Режим": "Mode", "Заново": "Restart",
    "Следующая фраза": "Next phrase", "Строгий режим": "Strict mode",
    "Клавиатура": "Keyboard", "Размер шрифта": "Font size",
    "Заглавные": "Capital letters", "Пунктуация": "Punctuation",
    "Цифры": "Digits", "Цветные зоны пальцев": "Colored finger zones",
    "Звук нажатий и ошибок": "Key and error sound",
    "Каретка темпа рекорда": "Record pace ghost",
    "Светлая / тёмная тема": "Light / dark theme",
    "после перезапуска": "after restart", "Выход": "Quit",
    "закрыть эту справку": "close this help",
    "открыть свой текст": "open custom text",
    "пропустить фразу": "skip phrase",
    "начать эту фразу заново": "restart the phrase",
    "показать / скрыть": "show / hide",
    "сбросить всю накопленную статистику": "reset all statistics",
    "длина теста": "test length", "увеличить / уменьшить текст": "font size +/-",
    "пауза — время не идёт, продолжайте печатать":
        "Paused — typing time is stopped, keep typing",
    "Включена другая раскладка": "Wrong system layout",
    "переключите на": "switch to", "Включён Caps Lock": "Caps Lock is on",
    "выключите его": "turn it off",
    "Статистика сброшена": "Statistics reset",
    "Сбросить всю статистику": "Reset all statistics",
    "Нажмите F7 ещё раз": "Press F7 again",
    "Тема сохранена": "Theme saved", "перезапустите приложение": "restart the app",
    "Всего": "Total", "тестов": "tests", "теста": "tests", "тест": "test",
    "слов/мин": "WPM", "точности": "accuracy",
    "ошибок": "errors", "ошибки": "errors", "ошибка": "error",
    "без ошибок": "no errors", "новый рекорд": "new record",
    "новая буква": "new letter", "любая клавиша": "any key",
    "лучшее комбо": "best combo", "пауза": "paused",
    "Начать": "Start", "Следующий": "Next",
    "Скорость и точность по дням": "Speed and accuracy by day",
    "Карта ошибок": "Error heatmap", "Последний результат": "Last result",
    "Слабые сочетания": "Weak bigrams", "Награды": "Awards",
    "Пока нет наград": "No awards yet",
    "Последние завершённые тесты": "Recent completed tests",
    "Закрыть": "Close", "Сегодня": "Today", "Серия": "Streak",
    "Пока мало данных": "Not enough data",
    "Пока нет завершённых тренировок": "No completed tests yet",
    "Ошибки": "Errors", "Самые медленные клавиши": "Slowest keys",
}


def translate(message: str, language: str = "ru") -> str:
    if language != "en":
        return message
    for original in sorted(ENGLISH, key=len, reverse=True):
        message = message.replace(original, ENGLISH[original])
    return message
