"""Keyboard layout and per-keystroke hint drawing for the Tk application."""

from __future__ import annotations

import tkinter as tk

from . import theme
from .layout import EQUIVALENTS, FINGER_NAMES, LAYOUTS, stroke_for
from .words import Mode

SHIFT_UNITS = 2.2
SPACE_UNITS = 7


class KeyboardMixin:
    # ------------------------------------------------------- клавиатура-подсказка

    def _on_kb_configure(self, event: tk.Event) -> None:
        # Высота тоже важна: в компактной плотности холст ниже, и клавиши,
        # посчитанные под старую высоту, вылезали бы за его край.
        size = (event.width, event.height)
        if size == self._kb_size:
            return
        self._kb_size = size
        if self._resize_id is not None:
            self.after_cancel(self._resize_id)
        self._resize_id = self.after(120, self._layout_keyboard)

    @property
    def _kb_full(self) -> bool:
        """Полная клавиатура (ряд цифр, знаки, Shift) — когда текст их требует."""
        return self.source.decorates or self.mode is Mode.CUSTOM

    def _kb_height(self) -> int:
        d = self.density
        return d.kb_h + (d.kb_extra if self._kb_full else 0)

    def _keyboard_code(self) -> str:
        """Selected physical keyboard, independent of text language."""
        return self.keyboard_variant if self.lang == "en" else self.lang

    def set_keyboard_variant(self, variant: str) -> None:
        if variant not in ("en", "dvorak", "colemak"):
            return
        if self.lang != "en":
            self.lang = "en"
        self.keyboard_variant = variant
        self._refresh_chips()
        self._layout_keyboard()
        self.new_test()
        self._persist()

    def _keyboard_rows(self) -> list[list[tuple[str, str, float, str]]]:
        """Ряды клавиш: (имя, подпись, ширина в клавишах, мелкая подпись Shift)."""
        layout = LAYOUTS[self._keyboard_code()]
        rows: list[list[tuple[str, str, float, str]]]
        if not self._kb_full:
            rows = [[(ch, ch.upper(), 1.0, "") for ch in row] for row in layout.display_rows]
        else:
            rows = []
            for plain, shifted in layout.full:
                # У букв «что под Shift» очевидно, подписываем только знаки.
                rows.append([(base, base.upper(), 1.0, "" if up == base.upper() else up)
                             for base, up in zip(plain, shifted)])
            rows[-1] = [("shift_left", "SHIFT", SHIFT_UNITS, ""), *rows[-1],
                        ("shift_right", "SHIFT", SHIFT_UNITS, "")]
        rows.append([(" ", "ПРОБЕЛ", SPACE_UNITS, "")])
        return rows

    def _layout_keyboard(self) -> None:
        """Пересобрать клавиши. Вызывается только при смене размера, языка
        или состава клавиатуры (опции текста)."""
        self._resize_id = None
        c = self.kb_canvas
        c.delete("all")
        self._kb_items.clear()
        self._kb_small.clear()
        self._hot_key = self._hot_shift = None
        self._kb_full_drawn = self._kb_full

        rows = self._keyboard_rows()
        width, height = c.winfo_width(), c.winfo_height()
        if width <= 1 or height <= 1:
            return
        gap = self.px(4)
        # Ширина «обычной» клавиши — по самому широкому ряду.
        kw = min(
            (width - self.px(40) - gap * (len(row) - 1)) / sum(u for _, _, u, _ in row)
            for row in rows
        )
        kw = min(self.px(46), kw)
        # Все ряды обязаны уместиться по высоте: раньше высота клавиш считалась
        # только от ширины, и в низком окне верхний ряд уходил за край холста.
        kh = min(self.px(34), kw, (height - (len(rows) - 1) * gap - self.px(2)) / len(rows))
        if kw < self.px(12) or kh < self.px(10):
            return
        top = max((height - (kh * len(rows) + gap * (len(rows) - 1))) / 2, 0)
        small_labels = kh >= self.px(24)
        # В сжатой клавиатуре (пять рядов в маленьком окне) подпись обычным
        # кеглем выше самой клавиши — берём мелкий.
        label_font = self.f_key if kh >= self.px(19) else self.f_key_small

        for r, row in enumerate(rows):
            widths = [u * kw + (u - 1) * gap for _, _, u, _ in row]
            x = (width - sum(widths) - gap * (len(row) - 1)) / 2
            y = top + r * (kh + gap)
            for (name, text, _, small), w in zip(row, widths):
                base_bg, base_fg = self._key_base(name)
                rect = c.create_rectangle(x, y, x + w, y + kh, fill=base_bg, width=0)
                label = c.create_text(x + w / 2, y + kh / 2, text=text,
                                      fill=base_fg, font=label_font)
                self._kb_items[name] = (rect, label)
                if small and small_labels:
                    self._kb_small[name] = c.create_text(
                        x + self.px(3), y + self.px(1), text=small, anchor="nw",
                        fill=theme.TEXT_FAINT, font=self.f_key_small)
                x += w + gap
        self._update_next_key()
        self._refresh_course_keys()

    def _paint_key(self, name: str | None, hot: bool) -> None:
        if name is None or name not in self._kb_items:
            return
        rect, label = self._kb_items[name]
        if hot:
            bg, fg, small = theme.KEY_NEXT_BG, theme.KEY_NEXT_FG, theme.KEY_NEXT_FG
        else:
            bg, fg = self._key_base(name)
            small = theme.TEXT_FAINT
        self.kb_canvas.itemconfigure(rect, fill=bg)
        self.kb_canvas.itemconfigure(label, fill=fg)
        if name in self._kb_small:
            self.kb_canvas.itemconfigure(self._kb_small[name], fill=small)

    def _update_next_key(self) -> None:
        """Подсветить следующую клавишу (и Shift другой рукой, если нужен)."""
        if not self.show_keyboard or not self._kb_items:
            return
        session = self.session
        ch = None
        if session and not session.finished and session.pos < len(session.target):
            ch = session.target[session.pos]
        stroke = stroke_for(self._keyboard_code(), ch) if ch else None
        key = stroke.key if stroke else (ch.lower() if ch else None)
        shift = f"shift_{stroke.shift_side}" if stroke and stroke.shift_side else None

        if (key, shift) == (self._hot_key, self._hot_shift):
            return
        self._paint_key(self._hot_key, False)
        self._paint_key(self._hot_shift, False)
        self._hot_key, self._hot_shift = key, shift
        self._paint_key(key, True)
        self._paint_key(shift, True)

        hint = FINGER_NAMES[stroke.finger] if stroke else ""
        if stroke and stroke.shift_side:
            hand = "правой" if stroke.shift_side == "right" else "левой"
            hint += f" + Shift {hand} рукой"
        alternative = EQUIVALENTS[self.lang].get(ch) if ch else None
        if hint and alternative:
            hint += f" · можно и «{alternative}»"
        self.finger_var.set(self._tr(hint))

