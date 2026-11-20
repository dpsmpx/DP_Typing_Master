"""Reusable combo drawing and animation methods for the Tk application."""

from __future__ import annotations

import tkinter as tk

from . import theme

ANIM_FRAMES = 8
ANIM_STEP_MS = 28


def _lerp_hex(a: str, b: str, t: float) -> str:
    """Линейная интерполяция двух цветов #rrggbb."""
    ar, ag, ab = int(a[1:3], 16), int(a[3:5], 16), int(a[5:7], 16)
    br, bg, bb = int(b[1:3], 16), int(b[3:5], 16), int(b[5:7], 16)
    r = round(ar + (br - ar) * t)
    g = round(ag + (bg - ag) * t)
    b = round(ab + (bb - ab) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


class ComboMixin:
    # ------------------------------------------------------------------ комбо

    def _fade(self, flash: str, base: str) -> tuple[str, ...]:
        """Градиент вспышки, посчитанный один раз на пару цветов."""
        key = (flash, base)
        ramp = self._fade_cache.get(key)
        if ramp is None:
            ramp = tuple(
                _lerp_hex(flash, base, i / (ANIM_FRAMES - 1)) for i in range(ANIM_FRAMES)
            )
            self._fade_cache[key] = ramp
        return ramp

    def _on_combo_configure(self, event: tk.Event) -> None:
        self._combo_w = event.width
        self._combo_h = event.height
        self._combo_tier = None          # заставить пересобрать геометрию
        self._combo_bar_right = -1
        self._draw_combo()

    def _combo_rows(self) -> tuple[int, int, int]:
        """Вертикальные позиции: число, подпись, полоска (под высоту холста)."""
        h = self._combo_h
        return round(h * 0.35), round(h * 0.68), h - self.px(10)

    def _draw_combo(self, pulse: bool = False) -> None:
        width = self._combo_w
        if width <= 1:
            return
        session = self.session
        combo = session.combo if session else 0
        tier = theme.combo_tier(combo)
        c = self.combo_canvas
        mid = width // 2
        value_y, caption_y, bar_y = self._combo_rows()
        bar_h = self.px(3)
        bar_w = min(self.px(320), width - self.px(80))
        left = mid - bar_w // 2

        # Тяжёлая часть — подписи и позиции — трогается только когда сменился
        # уровень комбо или размер окна, а не на каждое нажатие.
        if tier is not self._combo_tier:
            self._combo_tier = tier
            c.coords(self._combo_value, mid, value_y)
            c.coords(self._combo_caption, mid, caption_y)
            caption = f"КОМБО · {tier.name.upper()}" if tier.name else "КОМБО"
            c.itemconfigure(self._combo_caption, text=caption, fill=tier.color)
            c.itemconfigure(self._combo_bar, fill=tier.color)
            c.coords(self._combo_bar_bg, left, bar_y, left + bar_w, bar_y + bar_h)

        c.itemconfigure(self._combo_value, text=f"×{combo}" if combo else "—")

        nxt = theme.next_threshold(combo)
        filled = 1.0 if nxt is None else (combo - tier.threshold) / max(nxt - tier.threshold, 1)
        right = round(left + bar_w * filled)
        if right != self._combo_bar_right:      # меньше пикселя — не дёргаем Tk
            self._combo_bar_right = right
            c.coords(self._combo_bar, left, bar_y, right, bar_y + bar_h)

        if pulse:
            self._pulse_combo(tier)
        else:
            c.itemconfigure(self._combo_value, fill=tier.color, font=self.f_combo)

    def _pulse_combo(self, tier) -> None:
        """Запустить (или перезапустить) вспышку. В очереди всегда ≤ 1 кадр.

        Смена шрифта заставляет Tk заново обмерять текст, поэтому «подскок»
        размера делается только при переходе на новый уровень; обычное
        нажатие обходится сменой одного цвета.
        """
        self._anim_ramp = self._fade(tier.flash, tier.color)
        self._anim_frame = 0
        if tier is not self._pulsed_tier:
            self._pulsed_tier = tier
            self.combo_canvas.itemconfigure(self._combo_value, fill=tier.flash,
                                            font=self.f_combo_big)
        else:
            self.combo_canvas.itemconfigure(self._combo_value, fill=tier.flash)
        if self._anim_id is None:
            self._anim_id = self.after(ANIM_STEP_MS, self._anim_tick)

    def _anim_tick(self) -> None:
        self._anim_id = None
        self._anim_frame += 1
        if self._anim_frame >= ANIM_FRAMES:
            self.combo_canvas.itemconfigure(self._combo_value, font=self.f_combo)
            return  # цепочка закончилась, очередь пуста
        if self._anim_frame == 2:
            self.combo_canvas.itemconfigure(self._combo_value,
                                            fill=self._anim_ramp[2], font=self.f_combo)
        else:
            self.combo_canvas.itemconfigure(self._combo_value,
                                            fill=self._anim_ramp[self._anim_frame])
        self._anim_id = self.after(ANIM_STEP_MS, self._anim_tick)
