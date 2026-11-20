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
    "КУРС": "COURSE", "ФОКУС": "FOCUS",
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


# Complete visible strings for menus, prompts, the results dashboard and hints.
# Whole phrases precede their component words in translate().
ENGLISH.update({
    "ПРОБЕЛ": "SPACE",
    "разогрев": "warmup", "в потоке": "in the zone", "разгон": "speeding up",
    "огонь": "on fire", "легенда": "legend",
    "левый мизинец": "left pinky", "левый безымянный": "left ring finger",
    "левый средний": "left middle finger",
    "левый указательный": "left index finger",
    "правый мизинец": "right pinky", "правый безымянный": "right ring finger",
    "правый средний": "right middle finger",
    "правый указательный": "right index finger", "большой": "thumb",
    "правой рукой": "with right hand", "левой рукой": "with left hand",
    "можно и": "also accepts",
    "Карта ошибок на клавиатуре": "Keyboard error heatmap",
    "Курс: следующая буква": "Course: next letter",
    "Прогресс": "Progress",
    "Курс: ★": "Course: ★",
    "Открыть следующую букву": "Unlock next letter",
    "Убрать последнюю букву": "Remove last letter",
    "Цель:": "Target:",
    "Открыты все буквы": "All letters unlocked",
    "Это начало курса": "This is the first stage",
    "одна фраза": "one phrase", "секунд": "seconds", "дн.": "days",
    "знака": "characters", "знаков": "characters", "знак": "character",
    "Скорость (до": "Speed (up to",
    "Точность (до 100%)": "Accuracy (up to 100%)",
    "Сегодня:": "Today:", "Серия:": "Streak:", "тренировок": "tests",
    "Карта ошибок — клавиатура": "Keyboard error heatmap",
    ("Зелёный — точно, жёлтый — 5%+ ошибок, красный — 20%+; "
     "серый — мало данных. Наведите на клавишу."): (
        "Green: accurate; yellow: 5%+ errors; red: 20%+; "
        "gray: too little data. Hover over a key."
    ),
    "нет": "none", "пока недостаточно данных": "not enough data yet",
    "Завершите тренировку, чтобы увидеть разбор ошибок и ритма.":
        "Complete a test to see error and timing details.",
    "Последние завершённые тесты": "Recent completed tests",
    "Первый завершённый тест": "First completed test",
    "Комбо 50": "Combo 50", "Комбо 100": "Combo 100",
    "Точность не ниже 98%": "Accuracy of at least 98%",
    "пауза — время не идёт, продолжайте печатать":
        "Paused — typing time is stopped; continue typing",
    "пропустить фразу / закрыть справку": "skip phrase / close help",
    "начать эту фразу заново": "restart the same phrase",
    "язык: русский / английский": "language: Russian / English",
    "режим тренировки": "training mode",
    "курс: открыть следующую букву / убрать последнюю":
        "course: unlock next letter / remove previous",
    "строгий режим (не пускает дальше при ошибке)": "strict mode (errors stop progress)",
    "показать / скрыть экранную клавиатуру": "show / hide the on-screen keyboard",
    "сбросить всю накопленную статистику": "reset all accumulated statistics",
    "длина теста: фраза, 10–100 слов, 15–120 секунд":
        "test length: phrase, 10–100 words, 15–120 seconds",
    "заглавные / знаки препинания / цифры": "capital letters / punctuation / digits",
    "открыть свой текст (.txt) и печатать его кусками":
        "open custom text (.txt) and practice in chunks",
    "прогресс, график, карта ошибок и дневная цель":
        "progress, chart, error heatmap and daily goal",
    "язык / режим / строго / клавиатура": "language / mode / strict / keyboard",
    "увеличить / уменьшить текст": "increase / decrease text size",
    "«Ё» засчитывается и нажатием «Е».": "You can type 'Е' instead of 'Ё'.",
    "После 5 секунд без нажатий время не идёт.":
        "The clock pauses after five seconds of inactivity.",
    "Тема сохранена — перезапустите приложение":
        "Theme saved — restart the application",
    "Язык интерфейса сохранён — перезапустите приложение":
        "Interface language saved — restart the application",
    "Язык задаёт открытый текст — Ctrl+O откроет другой":
        "The current text determines its language — press Ctrl+O to open another",
    "Текст пройден — начинаем сначала": "Text complete — starting again",
    "пример текста": "sample text", "открыть свой": "open your",
    "Открыть текст для тренировки": "Open a text file to practice",
    "Все файлы": "All files", "Текст": "Text",
    "Открыт": "Opened", "нет текста": "no text",
    "любая клавиша — дальше": "any key — continue",
    "Tab — ещё раз": "Tab — again", "F1 — справка": "F1 — help",
    "Esc — дальше": "Esc — next", "Tab — заново": "Tab — restart",
    "строгий режим включён": "strict mode enabled",
    "клавиатура скрыта (F6)": "keyboard hidden (F6)",
    "лучшее комбо": "best combo",
    "новая буква": "new letter",
    "Комбо": "Combo",
    "Статистика": "Statistics",
    "шаг": "step",
})


def translate(message: str, language: str = "ru") -> str:
    if language != "en":
        return message
    for original in sorted(ENGLISH, key=len, reverse=True):
        message = message.replace(original, ENGLISH[original])
    return message
