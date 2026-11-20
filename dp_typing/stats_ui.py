"""Reusable statistics widgets and live progress drawing behavior."""

from __future__ import annotations

import math
import tkinter as tk

from . import theme
from .fmt import count


class StatsMixin:
    # ---------------------------------------------------------------- метрики

    def _refresh_stats(self, force: bool = False) -> None:
        session = self.session
        if session is None:
            return
        m = session.metrics()
        values = {
            "wpm": f"{m.wpm:.0f}",
            "cpm": f"{m.cpm:.0f}",
            "acc": f"{m.accuracy:.0f}%",
            "err": str(m.errors),
            "best": f"{self.profile.record(self._record_key()):.0f}",
        }
        colors = {
            "acc": theme.accuracy_color(m.accuracy),
            "err": theme.BAD if m.errors else theme.TEXT,
        }
        remaining = session.remaining()
        if remaining is not None:
            values["extra"] = str(math.ceil(remaining))
            if remaining <= 5 and session.started and not session.finished:
                colors["extra"] = theme.WARN
        elif self.length.kind == "words":
            target = session.target
            done = len(target.split()) if session.finished else target.count(" ", 0, session.pos)
            values["extra"] = f"{done}/{len(target.split())}"
        for key, text in values.items():
            color = colors.get(key, theme.TEXT)
            cached = self._stat_cache.get(key)
            if force or cached != (text, color):
                # .configure — самая дорогая операция здесь, поэтому она
                # выполняется только когда значение реально изменилось.
                self.stat_vars[key].set(text)
                self.stat_labels[key].configure(fg=color)
                self._stat_cache[key] = (text, color)

        self._update_progress()

    def _on_progress_configure(self, event: tk.Event) -> None:
        self._progress_w = event.width
        self._update_progress()

    def _update_progress(self) -> None:
        """Самый горячий путь: одно перемещение прямоугольника."""
        session = self.session
        if self._progress_w > 1 and session is not None:
            filled = self._progress_w * session.pos / len(session.target)
            self.progress.coords(self._progress_bar, 0, 0, filled, self.px(3))
            record_wpm = self.profile.record(self._record_key()) if self.ghost_enabled else 0
            if record_wpm and session.started:
                expected_chars = session.elapsed() * record_wpm * 5 / 60
                ghost_x = min(self._progress_w - 2,
                              self._progress_w * expected_chars / len(session.target))
                self.progress.coords(self._ghost_marker, ghost_x, 0, ghost_x + 2,
                                     self.px(3))
            else:
                self.progress.coords(self._ghost_marker, 0, 0, 0, 0)

    def _refresh_session_line(self) -> None:
        p = self.profile
        if p.tests == 0:
            self.session_var.set("")
            return
        self.session_var.set(self._tr(
            f"Всего: {count(p.tests, 'тест', 'теста', 'тестов')} · {p.wpm:.0f} слов/мин · "
            f"{p.accuracy:.0f}% · лучшее комбо ×{p.best_combo}"
        ))
