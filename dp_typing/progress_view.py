"""On-demand progress dashboard: charts, error heatmap, goal and last result.

No repeated Tk callbacks: opening the dashboard reads the local SQLite file
once and renders static Tk widgets. The typing UI is free of background work.
"""

from __future__ import annotations

import tkinter as tk

from . import awards, progress, theme
from .layout import LAYOUTS


def chart_points(rows: list[dict], key: str, height: int,
                 top: float) -> list[float]:
    """Normalize daily WPM or accuracy values onto one zero-based Y axis."""
    if not rows or top <= 0:
        return []
    return [max(0.0, min(float(row.get(key) or 0), top)) / top * height for row in rows]


def _chart(parent: tk.Widget, rows: list[dict]) -> None:
    canvas = tk.Canvas(parent, bg=theme.PANEL, height=230, highlightthickness=0)
    canvas.pack(fill="x", padx=16, pady=(4, 12))
    canvas.update_idletasks()
    w = max(canvas.winfo_width(), 640)
    left, right, top, bottom = 44, w - 24, 20, 192
    for i in range(5):
        y = top + (bottom - top) * i / 4
        canvas.create_line(left, y, right, y, fill=theme.BORDER)
    if not rows:
        canvas.create_text(w / 2, 110, text="Пока нет завершённых тренировок",
                           fill=theme.TEXT_DIM)
        return
    max_wpm = max(60.0, max(float(row["wpm"]) for row in rows) * 1.2)
    for key, color, maximum in (("wpm", theme.ACCENT, max_wpm),
                                ("accuracy", theme.GOOD, 100.0)):
        normalized = chart_points(rows, key, bottom - top, maximum)
        points = []
        for i, y in enumerate(normalized):
            x = left + (right - left) * i / max(len(rows) - 1, 1)
            points.extend((x, bottom - y))
            canvas.create_oval(x - 3, bottom - y - 3, x + 3, bottom - y + 3,
                               fill=color, outline=color)
        if len(points) >= 4:
            canvas.create_line(*points, fill=color, width=2)
    canvas.create_text(left, 209, text=rows[0]["day"], fill=theme.TEXT_DIM,
                       anchor="w")
    canvas.create_text(right, 209, text=rows[-1]["day"], fill=theme.TEXT_DIM,
                       anchor="e")
    canvas.create_text(left, 10, text=f"Скорость (до {max_wpm:.0f})",
                       fill=theme.ACCENT, anchor="w")
    canvas.create_text(right, 10, text="Точность (до 100%)",
                       fill=theme.GOOD, anchor="e")


def _heading(parent: tk.Widget, text: str) -> None:
    tk.Label(parent, text=text, bg=theme.BG, fg=theme.TEXT,
             font=("TkDefaultFont", 12, "bold")).pack(anchor="w", padx=16, pady=(14, 4))


def _heatmap(parent: tk.Widget, app) -> None:
    for row in LAYOUTS[app.lang].display_rows:
        frame = tk.Frame(parent, bg=theme.BG)
        frame.pack(anchor="center")
        for ch in row:
            total = app.profile.char_total[ch]
            errors = app.profile.char_errors[ch]
            rate = errors / total if total else 0.0
            color = (theme.KEY_BG if total < 4 else
                     theme.BAD if rate >= 0.2 else
                     theme.WARN if rate >= 0.05 else theme.GOOD)
            label = tk.Label(frame, text=ch.upper(), bg=color,
                             fg=theme.BG if total >= 4 else theme.TEXT_DIM,
                             width=3, padx=2, pady=6)
            label.pack(side="left", padx=2, pady=2)
            label.bind("<Enter>", lambda _e, item=label, c=ch:
                       item.configure(text=f"{app.profile.char_errors[c]}/"
                                           f"{app.profile.char_total[c]}"))
            label.bind("<Leave>", lambda _e, item=label, c=ch:
                       item.configure(text=c.upper()))


def show(app) -> tk.Toplevel:
    window = tk.Toplevel(app)
    window.title("DP Typing Master — прогресс")
    window.configure(bg=theme.BG)
    window.geometry("860x810")
    window.minsize(600, 500)
    scroll = tk.Canvas(window, bg=theme.BG, highlightthickness=0)
    bar = tk.Scrollbar(window, orient="vertical", command=scroll.yview)
    scroll.configure(yscrollcommand=bar.set)
    bar.pack(side="right", fill="y")
    scroll.pack(side="left", fill="both", expand=True)
    content = tk.Frame(scroll, bg=theme.BG)
    item = scroll.create_window((0, 0), window=content, anchor="nw")
    content.bind("<Configure>", lambda _e: scroll.configure(
        scrollregion=scroll.bbox("all")))
    scroll.bind("<Configure>", lambda e: scroll.itemconfigure(item, width=e.width))

    goal = progress.daily_goal()
    _heading(content, "ПРОГРЕСС")
    tk.Label(content, bg=theme.BG, fg=theme.TEXT_DIM,
             text=(f"Сегодня: {goal['done']}/{goal['goal']} тренировок · "
                   f"Серия: {goal['streak']} дн.")).pack(anchor="w", padx=16)
    _heading(content, "Скорость и точность по дням")
    _chart(content, progress.daily(30))

    _heading(content, "Карта ошибок — клавиатура")
    tk.Label(content, bg=theme.BG, fg=theme.TEXT_DIM,
             text="Зелёный — точно, жёлтый — 5%+ ошибок, красный — 20%+; "
                  "серый — мало данных. Наведите на клавишу.").pack(
                      anchor="w", padx=16, pady=6)
    _heatmap(content, app)

    _heading(content, "Слабые сочетания")
    pairs = app.profile.weak_bigrams()
    tk.Label(content, bg=theme.BG, fg=theme.TEXT_DIM, wraplength=780,
             text=(", ".join(f"{pair}: {rate:.0%}" for pair, rate in pairs)
                   if pairs else "Пока мало данных")).pack(anchor="w", padx=16)

    _heading(content, "Награды")
    unlocked = sorted(app.achievements)
    label = (", ".join(awards.MILESTONES[k] for k in unlocked)
             if unlocked else "Пока нет наград")
    stars = awards.stars(app.course[app.lang])
    tk.Label(content, bg=theme.BG, fg=theme.TEXT_DIM,
             text=f"Курс: ★ {stars} · {label}", wraplength=780).pack(
                 anchor="w", padx=16)

    _heading(content, "Последний результат")
    session = app.session
    if session is not None and session.finished:
        errors = sorted(session.char_errors.items(), key=lambda item: -item[1])
        speeds = sorted(((ch, session.char_time[ch] / n)
                         for ch, n in session.char_time_n.items() if n),
                        key=lambda item: -item[1])
        detail = ("Ошибки: " + (", ".join(f"{ch} ×{n}" for ch, n in errors[:12])
                                if errors else "нет") + "\n"
                  + "Самые медленные клавиши: "
                  + (", ".join(f"{ch} {t:.2f} с" for ch, t in speeds[:8])
                     if speeds else "пока недостаточно данных"))
    else:
        detail = "Завершите тренировку, чтобы увидеть разбор ошибок и ритма."
    tk.Label(content, bg=theme.BG, fg=theme.TEXT_DIM, justify="left",
             text=detail, wraplength=780).pack(anchor="w", padx=16, pady=(3, 12))

    _heading(content, "Последние завершённые тесты")
    for row in progress.recent(10):
        text = (f"{row['created_at'][:16]} · {row['lang']}/{row['mode']} · "
                f"{row['wpm']:.0f} слов/мин · {row['accuracy']:.0f}% · "
                f"{row['errors']} ошибок")
        tk.Label(content, bg=theme.BG, fg=theme.TEXT_DIM,
                 text=text).pack(anchor="w", padx=16, pady=2)
    tk.Button(content, text="Закрыть", command=window.destroy).pack(pady=20)
    window.transient(app)
    window.focus_set()
    return window
