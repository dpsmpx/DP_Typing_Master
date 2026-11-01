"""Режим «Свой текст»: книга или статья, которую печатают кусками.

Без tkinter — проверяется headless. Идея — из Amphetype и TIPP10: навык
лучше всего переносится на реальную работу, когда печатаешь реальный текст,
а не наборы слов.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from .layout import alphabet_of, stroke_for
from .words import Length

#: Встроенные примеры — на случай, когда свой текст ещё не открыт.
SAMPLE_FILES = {"ru": "sample_ru.txt", "en": "sample_en.txt"}

#: Больше этого не читаем: это уже не текст для тренировки, а что-то не то.
MAX_FILE_BYTES = 5 * 1024 * 1024
#: Короче этого после очистки — тренироваться не на чем.
MIN_TEXT_CHARS = 20
#: «Фраза» из своего текста — до конца предложения, но в этих пределах.
PHRASE_MIN_CHARS = 60
PHRASE_MAX_CHARS = 140
#: Знаков в секунду на потолке скорости: столько текста готовить к тесту на время.
CHARS_PER_SECOND = 25

#: Типографика, которой нет на клавиатуре, — в то, что на ней есть.
_REPLACE = {
    "«": '"', "»": '"', "„": '"', "“": '"', "”": '"', "‟": '"',
    "‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'",
    "—": "-", "–": "-", "‒": "-", "−": "-", "‐": "-", "‑": "-",
    "…": "...",
}
#: Невидимые символы, которые в тексте есть, а набрать их нельзя.
_DROP = {"­", "​", "‌", "‍", "⁠", "﻿"}
_SPACES = re.compile(r"\s+")
_SENTENCE_END = ".!?"


def normalize(raw: str) -> str:
    """Привести текст к тому, что можно набрать: кавычки «ёлочки» → прямые,
    длинное тире → дефис, многоточие → три точки, переносы строк → пробелы."""
    text = unicodedata.normalize("NFC", raw)
    text = "".join(_REPLACE.get(ch, ch) for ch in text if ch not in _DROP)
    return _SPACES.sub(" ", text).strip()


def detect_lang(text: str) -> str:
    """Язык по большинству букв: кириллица — русский, иначе английский."""
    counts = {"ru": 0, "en": 0}
    for ch in text:
        lang = alphabet_of(ch)
        if lang is not None:
            counts[lang] += 1
    return "ru" if counts["ru"] >= counts["en"] else "en"


def typeable(text: str, lang: str) -> str:
    """Оставить только слова, которые набираются на раскладке ``lang``.

    Слово с чужой буквой (латиница в русском тексте, эмодзи) выпадает
    целиком: иначе пришлось бы на полуслове переключать раскладку.
    """
    words = [w for w in text.split(" ")
             if w and all(stroke_for(lang, ch) is not None for ch in w)]
    return " ".join(words)


def decode(data: bytes) -> str:
    """UTF-8 (в том числе с BOM), иначе cp1251 — так часто сохранены русские
    тексты из Windows."""
    for encoding in ("utf-8-sig", "cp1251"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


class CustomTextError(ValueError):
    """Файл не годится для тренировки — с объяснением для пользователя."""


@dataclass
class CustomText:
    """Загруженный текст и место, где остановились."""

    title: str
    text: str
    lang: str
    position: int = 0

    @classmethod
    def from_file(cls, path: Path) -> CustomText:
        try:
            size = path.stat().st_size
            if size > MAX_FILE_BYTES:
                raise CustomTextError("Файл больше 5 МБ — это не похоже на текст")
            raw = decode(path.read_bytes())
        except OSError as exc:
            raise CustomTextError(f"Не удалось прочитать файл: {exc.strerror or exc}") from exc
        return cls.from_string(raw, title=path.stem)

    @classmethod
    def from_string(cls, raw: str, title: str) -> CustomText:
        text = normalize(raw)
        lang = detect_lang(text)
        text = typeable(text, lang)
        if len(text) < MIN_TEXT_CHARS:
            raise CustomTextError("В файле нет текста, который можно набрать")
        return cls(title=title, text=text, lang=lang)

    @property
    def progress(self) -> float:
        """Доля пройденного текста, 0..1."""
        return min(self.position / len(self.text), 1.0) if self.text else 0.0

    def chunk(self, length: Length) -> str:
        """Следующий кусок для теста заданной длины, начиная с ``position``."""
        if self.position >= len(self.text):
            self.position = 0
        return take(self.text, self.position, length)

    def advance(self, chunk: str, typed: int, finished: bool) -> bool:
        """Сдвинуть закладку после теста. True — текст пройден и начат заново.

        Дописанный (или пропущенный) кусок сдвигает закладку целиком; тест на
        время — до начала первого недописанного слова.
        """
        if finished or typed >= len(chunk):
            step = len(chunk) + 1                     # и пробел после куска
        else:
            # Слово, набранное до конца, пройдено, даже если пробел за ним
            # ещё не нажат: поэтому ищем пробел и на позиции ``typed``.
            space = chunk.rfind(" ", 0, typed + 1)
            step = 0 if space < 0 else space + 1
        self.position += step
        if self.position >= len(self.text):
            self.position = 0
            return True
        return False


def take(text: str, start: int, length: Length) -> str:
    """Кусок текста от ``start`` по словам, под длину теста."""
    end = start
    words = 0
    limit_chars = length.amount * CHARS_PER_SECOND if length.timed else None
    while end < len(text):
        space = text.find(" ", end)
        stop = len(text) if space < 0 else space
        words += 1
        size = stop - start
        end = stop
        if length.kind == "words" and words >= length.amount:
            break
        if limit_chars is not None and size >= limit_chars:
            break
        if length.kind == "phrase" and (
                size >= PHRASE_MAX_CHARS
                or (size >= PHRASE_MIN_CHARS and text[stop - 1] in _SENTENCE_END)):
            break
        end += 1                                      # перешагнуть пробел
    return text[start:end].rstrip(" ")


def sample(lang: str) -> CustomText:
    """Встроенный пример текста для языка — пока свой не открыт (Ctrl+O)."""
    from importlib.resources import files

    raw = (files("dp_typing.data") / SAMPLE_FILES[lang]).read_text(encoding="utf-8")
    return CustomText.from_string(raw, title="Пример текста" if lang == "ru" else "Sample text")
