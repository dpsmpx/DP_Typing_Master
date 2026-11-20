# Источники словарей

`ru_common.txt` и `en_common.txt` — частотная лексика, отобранная из
[hermitdave/FrequencyWords](https://github.com/hermitdave/FrequencyWords)
(корпус субтитров OpenSubtitles 2018, лицензия MIT).

Как получены списки:

1. взят частотный срез `ru_50k.txt` / `en_50k.txt`;
2. оставлены слова длиной 2–12 символов, целиком из букв своего алфавита
   и содержащие хотя бы одну гласную;
3. отброшена обсценная лексика;
4. взяты 1200 самых частотных;
5. в русский список добавлена дюжина слов с «ъ» — эта буква встречается
   в частотном срезе только начиная с ранга ~1060, и без добавки часть
   алфавита осталась бы без тренировки.

Оба списка покрывают алфавит целиком: 33 буквы для русского, 26 для
английского. Лицензия MIT совместима с GPL-3.0 этого проекта.

## Additional starter languages (November 2026)

`uk_common.txt` and `be_common.txt` are small manually assembled starter
lexicons for offline Ukrainian and Belarusian training. They are **not**
frequency-ranked 1200-word dictionaries; linguistic review and expansion remain
necessary before they can claim parity with ru/en. Example files are bundled.
