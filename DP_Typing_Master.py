```python
import tkinter as tk
from tkinter import font
import random
import time


class WordGenerator:
    def __init__(self, language="ru"):
        self.language = language
        self.russian_consonants = "бвгджзклмнпрстфхцчшщ"
        self.russian_vowels = "аеёиоуыэюя"
        self.english_consonants = "bcdfghjklmnpqrstvwxyz"
        self.english_vowels = "aeiouy"

        # Паттерны для генерации слогов (C - согласная, V - гласная)
        self.patterns = [
            ["C", "V"],
            ["C", "C", "V"],
            ["C", "V", "C"],
            ["V", "C"],
            ["V", "C", "C"],
            ["C", "V", "V"],
            ["C", "C", "V", "C"],
        ]

    def generate_word(self, min_syllables=1, max_syllables=3):
        syllables = []
        num_syllables = random.randint(min_syllables, max_syllables)

        for _ in range(num_syllables):
            pattern = random.choice(self.patterns)
            syllable = []
            for p in pattern:
                if p == "C":
                    syllable.append(self._get_consonant())
                else:
                    syllable.append(self._get_vowel())
            syllables.append("".join(syllable))

        word = "".join(syllables)
        return self._apply_modifications(word)

    def _get_consonant(self):
        if self.language == "ru":
            return random.choice(self.russian_consonants)
        return random.choice(self.english_consonants)

    def _get_vowel(self):
        if self.language == "ru":
            return random.choice(self.russian_vowels)
        return random.choice(self.english_vowels)

    def _apply_modifications(self, word):
        # Добавляем случайные модификации к слову
        modifications = [
            lambda w: w.capitalize(),
            lambda w: w
            + random.choice(
                ["ов", "ич", "ский"] if self.language == "ru" else ["ing", "ed", "s"]
            ),
            lambda w: w[: len(w) // 2]
            + random.choice(["ъ", "ь", ""] if self.language == "ru" else ["x", "z", ""])
            + w[len(w) // 2 :],
            lambda w: w,
        ]
        return random.choice(modifications)(word)

    def generate_phrase(self, word_count=4):
        return " ".join([self.generate_word() for _ in range(word_count)])


def calculate_stats(original, entered, time_taken):
    correct = 0
    errors = 0
    min_len = min(len(original), len(entered))

    for i in range(min_len):
        if original[i] == entered[i]:
            correct += 1
        else:
            errors += 1

    errors += max(len(original) - min_len, 0)
    errors += max(len(entered) - min_len, 0)

    total_chars = len(original)
    accuracy = (correct / total_chars) * 100 if total_chars > 0 else 0
    time_minutes = time_taken / 60
    cpm = (correct / time_minutes) if time_minutes > 0 else 0

    return accuracy, cpm, errors


class TypingTrainerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Blind Typing Trainer")
        self.configure(bg="black")
        self.geometry("800x600")

        # Configure styles
        self.bold_font = font.Font(family="Arial", size=14, weight="bold")
        self.main_font = font.Font(family="Courier", size=24, weight="bold")
        self.stat_font = font.Font(family="Verdana", size=12)

        # Statistics bar
        self.stat_frame = tk.Frame(self, bg="#1a1a1a", height=40)
        self.stat_frame.pack(fill="x", padx=10, pady=5)

        self.speed_label = tk.Label(
            self.stat_frame,
            text="Speed: 0 CPM",
            fg="white",
            bg="#1a1a1a",
            font=self.stat_font,
        )
        self.speed_label.pack(side="left", padx=20)

        self.accuracy_label = tk.Label(
            self.stat_frame,
            text="Accuracy: 100%",
            fg="white",
            bg="#1a1a1a",
            font=self.stat_font,
        )
        self.accuracy_label.pack(side="left", padx=20)

        self.errors_label = tk.Label(
            self.stat_frame,
            text="Errors: 0",
            fg="white",
            bg="#1a1a1a",
            font=self.stat_font,
        )
        self.errors_label.pack(side="left", padx=20)

        # Main text area
        self.text_frame = tk.Frame(self, bg="black")
        self.text_frame.pack(expand=True, fill="both", padx=50, pady=50)

        self.target_text = tk.Label(
            self.text_frame,
            text="",
            fg="white",
            bg="black",
            font=self.main_font,
            wraplength=700,
        )
        self.target_text.pack(expand=True)

        # Input area
        self.input_entry = tk.Entry(
            self,
            font=self.main_font,
            bg="#333",
            fg="white",
            insertbackground="white",
            justify="center",
        )
        self.input_entry.pack(fill="x", padx=50, pady=20)
        self.input_entry.bind("<KeyRelease>", self.check_input)

        # Initialize logic
        self.word_generator = WordGenerator()
        self.current_language = "ru"
        self.start_time = None
        self.running = False
        self.new_test()

    def new_test(self):
        self.current_language = "en" if self.current_language == "ru" else "ru"
        self.word_generator.language = self.current_language
        phrase = self.word_generator.generate_phrase(random.randint(4, 6))
        self.target_text.config(text=phrase)
        self.input_entry.delete(0, "end")
        self.input_entry.config(fg="white")
        self.start_time = None
        self.running = False

    def check_input(self, event):
        if not self.running:
            self.running = True
            self.start_time = time.time()

        input_text = self.input_entry.get()
        target = self.target_text.cget("text")

        # Update text colors
        self.input_entry.config(fg="white")
        for i, (input_char, target_char) in enumerate(zip(input_text, target)):
            if input_char != target_char:
                self.input_entry.config(fg="red")
                break

        # Check completion
        if len(input_text) == len(target) and input_text == target:
            self.show_results()

    def show_results(self):
        end_time = time.time()
        time_taken = end_time - self.start_time
        input_text = self.input_entry.get()
        target_text = self.target_text.cget("text")

        accuracy, cpm, errors = calculate_stats(target_text, input_text, time_taken)

        # Update statistics
        self.speed_label.config(text=f"Speed: {cpm:.0f} CPM")
        self.accuracy_label.config(text=f"Accuracy: {accuracy:.1f}%")
        self.errors_label.config(text=f"Errors: {errors}")

        # Schedule next test
        self.after(2000, self.new_test)

    def run(self):
        self.mainloop()


# Класс WordGenerator остается без изменений (из предыдущего ответа)
# Функция calculate_stats остается без изменений (из первого ответа)

if __name__ == "__main__":
    app = TypingTrainerApp()
    app.run()
```