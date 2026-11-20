"""Rebuild the offline Belarusian word list from a documented frequency corpus.

Usage:
    python tools/build_be_corpus.py > dp_typing/data/be_common.txt
    python tools/build_be_corpus.py --ci-preview

The source is third-party CC BY-SA 4.0 data; see dp_typing/data/SOURCES.md.
This tool is only for maintainers, not used at runtime.
"""

from __future__ import annotations

import gzip
import sys
import urllib.request

SOURCE = (
    "https://raw.githubusercontent.com/wasi-master/wmkeyboard-data/"
    "master/data/be/be_full.txt.gz"
)
LETTERS = set("абвгдеёжзійклмнопрстуўфхцчшыьэюя")
VOWELS = set("аеёіоуыэюя")


def make_words(data: bytes) -> list[str]:
    lines = gzip.decompress(data).decode("utf-8").splitlines()
    result: list[str] = []
    seen: set[str] = set()
    for line in lines:
        word = line.strip().split()[0].lower() if line.strip() else ""
        if not 2 <= len(word) <= 12:
            continue
        if word in seen or not set(word) <= LETTERS or not set(word) & VOWELS:
            continue
        seen.add(word)
        result.append(word)
        if len(result) == 1200:
            break
    if len(result) != 1200 or not set("".join(result)) >= LETTERS:
        raise ValueError("Source did not yield 1200 alphabet-covering Belarusian words")
    return result


def main() -> None:
    request = urllib.request.Request(SOURCE, headers={
        "User-Agent": "DP-Typing-Master/3.0 (+https://github.com/dpsmpx/DP_Typing_Master)"
    })
    with urllib.request.urlopen(request, timeout=50) as response:
        words = make_words(response.read())
    if "--ci-preview" in sys.argv:
        print("BE_WORDS_BEGIN", flush=True)
        for word in words:
            print("BE_WORD " + word)
        print("BE_WORDS_END", flush=True)
    else:
        print("\n".join(words))


if __name__ == "__main__":
    main()
