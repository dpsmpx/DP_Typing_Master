"""Режим «Свой текст»: очистка, язык, нарезка, закладка."""

import pytest

from dp_typing.customtext import (
    PHRASE_MAX_CHARS,
    PHRASE_MIN_CHARS,
    CustomText,
    CustomTextError,
    decode,
    detect_lang,
    normalize,
    sample,
    take,
    typeable,
)
from dp_typing.layout import stroke_for
from dp_typing.words import Length

PHRASE, W3, T1 = Length("phrase"), Length("words", 3), Length("time", 1)


def test_typography_becomes_typeable():
    raw = "«Ёлки» — это ёлки…\n\nНу\tда, «так»­.​"
    assert normalize(raw) == '"Ёлки" - это ёлки... Ну да, "так".'


def test_language_is_detected_by_majority():
    assert detect_lang("Привет, это обычный русский текст с парой слов in English") == "ru"
    assert detect_lang("Plain English text with many more words than this: два слова") == "en"


def test_foreign_words_are_dropped_whole():
    assert typeable("Он открыл Python и ушёл 🙂 домой", "ru") == "Он открыл и ушёл домой"
    assert typeable("Он сказал: «да»", "ru") == "Он сказал:"   # «ёлочки» без normalize не набрать


def test_everything_left_is_typeable():
    """Любой мусор на входе — на выходе только набираемое (берём этот же файл)."""
    from pathlib import Path

    raw = Path(__file__).read_text(encoding="utf-8") + " Русские слова тоже есть."
    text = CustomText.from_string(raw, title="t").text
    assert all(stroke_for(detect_lang(text), ch) for ch in text)


def test_decode_tries_utf8_then_cp1251():
    assert decode("ёжик".encode()) == "ёжик"
    assert decode("﻿ёжик".encode()) == "ёжик"          # BOM снят
    assert decode("ёжик".encode("cp1251")) == "ёжик"


def test_empty_or_foreign_file_is_rejected():
    with pytest.raises(CustomTextError):
        CustomText.from_string("🙂🙂🙂 ☃", title="t")


def test_file_errors_are_explained(tmp_path):
    with pytest.raises(CustomTextError, match="прочитать"):
        CustomText.from_file(tmp_path / "нет такого.txt")
    path = tmp_path / "книга.txt"
    path.write_text("Мороз и солнце; день чудесный! " * 3, encoding="cp1251")
    text = CustomText.from_file(path)
    assert text.title == "книга" and text.lang == "ru"


# ----------------------------------------------------------------- нарезка

TEXT = ("Первое предложение довольно длинное, чтобы набрать нужный размер. "
        "Второе тоже есть. Третье предложение завершает этот текст.")


def test_phrase_ends_at_a_sentence_when_possible():
    chunk = take(TEXT, 0, PHRASE)
    assert chunk.endswith(".")
    assert PHRASE_MIN_CHARS <= len(chunk) <= PHRASE_MAX_CHARS


def test_phrase_without_sentence_end_is_capped():
    text = " ".join(["слово"] * 100)
    assert len(take(text, 0, PHRASE)) <= PHRASE_MAX_CHARS + len("слово")


def test_words_chunk_has_exact_count():
    assert take(TEXT, 0, W3) == "Первое предложение довольно"


def test_timed_chunk_has_enough_text():
    assert len(take(" ".join(["слово"] * 100), 0, T1)) >= 25


def test_chunks_cover_the_text_in_order():
    text = CustomText(title="t", text=TEXT, lang="ru")
    seen = []
    for _ in range(50):
        chunk = text.chunk(W3)
        seen.append(chunk)
        if text.advance(chunk, len(chunk), finished=True):
            break
    assert " ".join(seen) == TEXT
    assert text.position == 0                         # дошли до конца — сначала


def test_timed_test_resumes_from_the_first_unfinished_word():
    text = CustomText(title="t", text="один два три четыре пять", lang="ru")
    chunk = text.chunk(T1)
    text.advance(chunk, typed=6, finished=False)      # «один д» — «два» не дописано
    assert text.text[text.position:].startswith("два")
    chunk = text.chunk(T1)
    text.advance(chunk, typed=3, finished=False)      # «два» дописано без пробела
    assert text.text[text.position:].startswith("три")


def test_progress_is_a_fraction():
    text = CustomText(title="t", text=TEXT, lang="ru")
    assert text.progress == 0
    text.advance(text.chunk(W3), 0, finished=True)
    assert 0 < text.progress < 1


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_samples_are_clean_and_typeable(lang):
    text = sample(lang)
    assert text.lang == lang
    assert len(text.text) > 500
    assert all(stroke_for(lang, ch) for ch in text.text)
