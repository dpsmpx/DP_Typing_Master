"""Интерфейс тренажёра на tkinter.

Устройство и причины решений по производительности:

* отдельного поля ввода нет — нажатия ловятся привязкой на корневом окне,
  поэтому нечего синхронизировать между виджетами;
* целевой текст живёт в ``tk.Text`` и рисуется один раз за тест; на каждое
  нажатие перекрашиваются 2-3 позиции через теги, а не вся строка;
* пока тест не идёт, в очереди нет ни одного ``after`` — приложение в покое
  не потребляет процессор вообще. Итог фразы висит до нажатия клавиши, так что
  и таймер перехода не нужен;
* пока тест идёт, работает ровно один таймер на 200 мс (обновление метрик);
  при простое он засыпает до следующего нажатия;
* анимация комбо — одна самозавершающаяся цепочка кадров с заранее
  просчитанным градиентом, меняется цвет двух элементов Canvas без
  пересборки layout;
* каретка не мигает (``insertofftime=0``), что убирает периодическую
  перерисовку, которую Tk устраивает сам по себе.
"""

from __future__ import annotations

import random
import time
import tkinter as tk
from contextlib import suppress
from dataclasses import dataclass, replace
from tkinter import font as tkfont

from . import __version__, theme
from .engine import Mark, Profile, TypingSession
from .fmt import count, wrap_words
from .layout import (
    CAPS_LOCK,
    EQUIVALENTS,
    FINGER_NAMES,
    LAYOUTS,
    WRONG_LAYOUT,
    finger_for,
    input_problem,
)
from .storage import load as load_profile
from .storage import restore as restore_profile
from .storage import save as save_profile
from .words import Mode, TextSource, lesson_stages

#: Период обновления метрик во время теста, мс.
TICK_MS = 200
#: Кадры анимации комбо и шаг между ними.
ANIM_FRAMES = 8
ANIM_STEP_MS = 28
#: Слов во фразе.
WORDS_PER_TEST = 9
#: Точность, с которой урок повышает ступень.
STAGE_UP_ACCURACY = 96.0
#: Сколько ждать второго F7: сброс всей статистики только с подтверждением.
RESET_CONFIRM_MS = 3000
#: Сколько держится предупреждение о раскладке или Caps Lock после
#: последнего такого нажатия.
INPUT_NOTICE_MS = 4000
#: Короткие сообщения: «последняя ступень», «статистика сброшена».
INFO_NOTICE_MS = 2200

MODE_ORDER = (Mode.LESSON, Mode.COMMON, Mode.PSEUDO, Mode.ADAPTIVE)

# Размеры ниже — в пикселях при 96 dpi. На HiDPI они умножаются на масштаб
# экрана (см. TypingApp.px), а кегли в пунктах Tk масштабирует сам.
WINDOW_SIZE = (1040, 720)
MIN_WINDOW_SIZE = (760, 560)
BODY_PADX = 18
BODY_PADY = 14
TEXT_PADX = 28
#: Ниже этой высоты холста клавиши стали бы нечитаемыми (4 ряда по ~13 px).
KB_MIN_H = 64

#: Цвета плашки-уведомления: фон и текст.
NOTICE_COLORS = {
    "warn": (theme.WARN, theme.BG),
    "danger": (theme.BAD, theme.BG),
    "info": (theme.ACCENT, "#ffffff"),
}


@dataclass(frozen=True)
class Density:
    """Размеры интерфейса. Компактная плотность включается, когда содержимое
    не помещается в окно по высоте (маленькое окно или фраза в 3+ строки)."""

    target: int          # кегль фразы, пт
    stat: int            # кегль чисел в плитках, пт
    combo: int
    combo_big: int
    result: int
    combo_h: int         # высота холста комбо, px
    kb_h: int            # высота холста клавиатуры, px
    text_pady: int
    line_above: int      # spacing1 у Text: воздух над строкой
    line_below: int      # spacing3 у Text: воздух под строкой
    result_pady: int
    tile_pady: int
    gap: int             # базовый вертикальный зазор между секциями

    def scaled(self, k: float) -> Density:
        """Та же плотность для экрана в ``k`` раз плотнее 96 dpi."""
        if k == 1:
            return self
        pixels = ("combo_h", "kb_h", "text_pady", "line_above", "line_below",
                  "result_pady", "tile_pady", "gap")
        return replace(self, **{name: round(getattr(self, name) * k) for name in pixels})


NORMAL = Density(target=22, stat=21, combo=26, combo_big=31, result=13,
                 combo_h=74, kb_h=150, text_pady=24, line_above=6, line_below=10,
                 result_pady=16, tile_pady=10, gap=12)
COMPACT = Density(target=18, stat=16, combo=20, combo_big=24, result=12,
                  combo_h=56, kb_h=100, text_pady=12, line_above=3, line_below=6,
                  result_pady=8, tile_pady=5, gap=5)


def _lerp_hex(a: str, b: str, t: float) -> str:
    """Линейная интерполяция двух цветов #rrggbb."""
    ar, ag, ab = int(a[1:3], 16), int(a[3:5], 16), int(a[5:7], 16)
    br, bg, bb = int(b[1:3], 16), int(b[3:5], 16), int(b[5:7], 16)
    r = round(ar + (br - ar) * t)
    g = round(ag + (bg - ag) * t)
    b = round(ab + (bb - ab) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


class TypingApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.scale = self._detect_scale()
        self._normal = NORMAL.scaled(self.scale)
        self._compact = COMPACT.scaled(self.scale)
        self.density = self._normal

        self.title(f"DP Typing Master {__version__}")
        self.configure(bg=theme.BG)
        width, height, min_w, min_h = self._window_sizes()
        self.geometry(f"{width}x{height}")
        self.minsize(min_w, min_h)

        # ---- состояние
        self.rng = random.Random()
        self.profile = Profile()
        saved = load_profile()
        restore_profile(self.profile, saved)
        self.lang: str = saved.get("lang", "ru") if saved.get("lang") in LAYOUTS else "ru"
        try:
            self.mode = Mode(saved.get("mode", Mode.COMMON.value))
        except ValueError:
            self.mode = Mode.COMMON
        self.stage: int = int(saved.get("stage", 0) or 0)
        self.strict: bool = bool(saved.get("strict", False))
        self.show_keyboard: bool = bool(saved.get("show_keyboard", True))

        self.source = TextSource(self.lang, self.mode, self.stage, self.rng)
        self.session: TypingSession | None = None

        # ---- идентификаторы отложенных задач; None означает «в очереди пусто»
        self._tick_id: str | None = None
        self._anim_id: str | None = None
        self._resize_id: str | None = None
        self._fit_id: str | None = None
        self._notice_id: str | None = None
        self._anim_frame = 0
        self._anim_ramp: tuple[str, ...] = ()
        self._fade_cache: dict[tuple[str, str], tuple[str, ...]] = {}
        self._stat_cache: dict[str, tuple] = {}
        self._kb_items: dict[str, tuple[int, int]] = {}
        self._kb_size = (0, 0)
        self._hot_key: str | None = None
        # Ширины холстов кэшируются: winfo_width() — обращение к Tk, а в
        # горячем пути оно вызывалось на каждое нажатие.
        self._combo_w = 0
        self._combo_h = self.density.combo_h
        self._progress_w = 0
        # Фраза разбита на строки вручную (см. _render_target); _spans[pos] —
        # индексы Tk начала и конца символа ``pos``.
        self._lines: list[str] = []
        self._spans: list[tuple[str, str]] = []
        self._caret_pos: int | None = None
        # Тег каретки: обычный или «ошибка под кареткой» (строгий режим).
        self._caret_tag = "caret"
        self._compact_saving = 0
        self._fitting = False
        self._win_size = (0, 0)
        self._text_width = 0
        self._combo_tier = None
        self._pulsed_tier = None
        self._combo_bar_right = -1
        self._paused_shown = False
        self._notice_kind: str | None = None
        self.notice_shown = False
        # Итог фразы, убранный на время показа плашки: они занимают одно место.
        self._stashed_result: tuple[str, str] | None = None
        self._notice_style: tuple[str, str] | None = None
        self._reset_armed_until = 0.0
        # Флаг, а не winfo_ismapped(): тот меняется только после отрисовки,
        # и нажатие сразу после F1 проскочило бы в тест.
        self.help_open = False

        self._build_fonts()
        self._build_ui()
        self._bind_keys()

        self.protocol("WM_DELETE_WINDOW", self._quit)
        self.bind("<Configure>", self._on_window_configure)
        # Фокус на само окно: клавиши ловит корневая привязка,
        # отдельного поля ввода в приложении нет.
        self.focus_set()
        self.new_test()

    # ------------------------------------------------------------- масштаб

    def _detect_scale(self) -> float:
        """Во сколько раз экран плотнее обычных 96 dpi."""
        try:
            per_point = float(self.tk.call("tk", "scaling"))
        except (tk.TclError, ValueError):
            return 1.0
        factor = per_point / (96 / 72)
        # Небольшие отклонения (100 dpi вместо 96) не трогаем, иначе на
        # обычных экранах всё «поплыло» бы на пару пикселей.
        return round(factor, 2) if factor >= 1.25 else 1.0

    def px(self, value: float) -> int:
        """Пиксели при 96 dpi → пиксели этого экрана."""
        return round(value * self.scale)

    def _window_sizes(self) -> tuple[int, int, int, int]:
        """Стартовый и минимальный размер окна — с учётом масштаба и экрана."""
        screen_w, screen_h = self.winfo_screenwidth(), self.winfo_screenheight()
        width = min(self.px(WINDOW_SIZE[0]), max(screen_w - 40, 320))
        height = min(self.px(WINDOW_SIZE[1]), max(screen_h - 80, 240))
        return (width, height,
                min(self.px(MIN_WINDOW_SIZE[0]), width), min(self.px(MIN_WINDOW_SIZE[1]), height))

    # ------------------------------------------------------------ построение

    def _build_fonts(self) -> None:
        available = set(tkfont.families(self))
        mono = theme.pick_family(available, theme.MONO_FAMILIES)
        ui = theme.pick_family(available, theme.UI_FAMILIES)
        d = self.density
        self.f_target = tkfont.Font(family=mono, size=d.target)
        self.f_stat = tkfont.Font(family=ui, size=d.stat, weight="bold")
        self.f_caption = tkfont.Font(family=ui, size=9)
        self.f_chip = tkfont.Font(family=ui, size=10, weight="bold")
        self.f_hint = tkfont.Font(family=ui, size=9)
        self.f_combo = tkfont.Font(family=ui, size=d.combo, weight="bold")
        self.f_combo_big = tkfont.Font(family=ui, size=d.combo_big, weight="bold")
        self.f_key = tkfont.Font(family=mono, size=10)
        self.f_result = tkfont.Font(family=ui, size=d.result, weight="bold")

    def _build_ui(self) -> None:
        self.body = tk.Frame(self, bg=theme.BG)
        self.body.pack(fill="both", expand=True, padx=self.px(BODY_PADX),
                       pady=self.px(BODY_PADY))
        root = self.body

        self._build_header(root)
        self._build_stats(root)
        self._build_text(root)
        self._build_combo(root)
        self._build_keyboard(root)
        self._build_footer(root)
        self._build_help()
        self._apply_density()
        if self.show_keyboard:
            self._pack_keyboard()

    def _build_header(self, parent: tk.Frame) -> None:
        bar = tk.Frame(parent, bg=theme.BG)
        bar.pack(fill="x")
        self._header_bar = bar

        tk.Label(bar, text="DP TYPING MASTER", bg=theme.BG, fg=theme.TEXT,
                 font=self.f_chip).pack(side="left")

        chips = tk.Frame(bar, bg=theme.BG)
        chips.pack(side="left", padx=(self.px(18), 0))
        self.lang_var = tk.StringVar()
        self.mode_var = tk.StringVar()
        self.stage_var = tk.StringVar()
        self._chips: list[tk.Label] = []
        for var, cmd in ((self.lang_var, self.toggle_language),
                         (self.mode_var, self.cycle_mode),
                         (self.stage_var, self.next_stage)):
            chip = tk.Label(chips, textvariable=var, bg=theme.PANEL, fg=theme.TEXT_DIM,
                            font=self.f_chip, padx=self.px(10), pady=self.px(4),
                            cursor="hand2")
            chip.pack(side="left", padx=(0, self.px(8)))
            chip.bind("<Button-1>", lambda _e, c=cmd: c())
            self._chips.append(chip)

        # Итоги за всё время — отдельной строкой: в один ряд с чипами они не
        # влезали и обрезали название ступени.
        self.session_var = tk.StringVar()
        self._session_label = tk.Label(parent, textvariable=self.session_var, bg=theme.BG,
                                       fg=theme.TEXT_DIM, font=self.f_hint, anchor="e")
        self._session_label.pack(fill="x")
        self._refresh_chips()

    def _build_stats(self, parent: tk.Frame) -> None:
        row = tk.Frame(parent, bg=theme.BG)
        row.pack(fill="x")
        self._stats_row = row

        self.stat_vars: dict[str, tk.StringVar] = {}
        self.stat_labels: dict[str, tk.Label] = {}
        self.stat_tiles: list[tk.Frame] = []
        self._tile_parts: list[tuple[tk.Label, tk.Label]] = []
        tiles = (("wpm", "СЛОВ/МИН"), ("cpm", "ЗНАКОВ/МИН"), ("acc", "ТОЧНОСТЬ"),
                 ("err", "ОШИБКИ"), ("best", "РЕКОРД"))
        for i, (key, caption) in enumerate(tiles):
            tile = tk.Frame(row, bg=theme.PANEL)
            # Плитки в чётных колонках с общей группой uniform — одинаковой
            # ширины, как бы ни были длинны подписи; нечётные колонки —
            # фиксированные зазоры, так что край ряда совпадает с краем фразы.
            tile.grid(row=0, column=2 * i, sticky="nsew")
            row.columnconfigure(2 * i, weight=1, uniform="tile")
            if i < len(tiles) - 1:
                row.columnconfigure(2 * i + 1, minsize=self.px(8))
            var = tk.StringVar(value="0")
            value = tk.Label(tile, textvariable=var, bg=theme.PANEL, fg=theme.TEXT,
                             font=self.f_stat, anchor="w")
            value.pack(fill="x", padx=self.px(14))
            cap = tk.Label(tile, text=caption, bg=theme.PANEL, fg=theme.TEXT_FAINT,
                           font=self.f_caption, anchor="w")
            cap.pack(fill="x", padx=self.px(14))
            self.stat_vars[key] = var
            self.stat_labels[key] = value
            self.stat_tiles.append(tile)
            self._tile_parts.append((value, cap))

        bar_h = self.px(3)
        self.progress = tk.Canvas(parent, height=bar_h, bg=theme.PANEL, highlightthickness=0)
        self.progress.pack(fill="x")
        self._progress_bar = self.progress.create_rectangle(
            0, 0, 0, bar_h, fill=theme.ACCENT, width=0
        )
        self.progress.bind("<Configure>", self._on_progress_configure)

    def _build_text(self, parent: tk.Frame) -> None:
        # fill="x" (а не "both"): панель берёт высоту по содержимому.
        # anchor="n": верх панели стоит на месте, когда фраза в одну строку
        # сменяется фразой в две, — раньше панель прыгала по вертикали.
        wrap = tk.Frame(parent, bg=theme.PANEL)
        wrap.pack(fill="x", expand=True, anchor="n")
        self._text_wrap = wrap

        self.text = tk.Text(
            wrap, bg=theme.PANEL, fg=theme.PENDING, font=self.f_target,
            wrap="word", relief="flat", highlightthickness=0, borderwidth=0,
            padx=self.px(TEXT_PADX), pady=self.density.text_pady,
            spacing1=self.density.line_above, spacing3=self.density.line_below,
            cursor="arrow", insertofftime=0, insertwidth=0, takefocus=0,
            # Text по умолчанию просит 24 строки — при кегле 22 это выше всего
            # окна, и pack не оставил бы места клавиатуре. Просим минимум,
            # реальную высоту выставляет _fit_text_height.
            width=1, height=4,
        )
        self.text.pack(fill="x")
        self.text.bind("<Configure>", self._on_text_configure)
        # Выравнивание — не justify=center, а отступом каждой строки (см.
        # _render_target): при центрировании Tk растягивал фон первого
        # символа строки до левого края, и каретка становилась полосой.
        self.text.tag_configure("base", foreground=theme.PENDING)
        self.text.tag_configure("ok", foreground=theme.CORRECT)
        self.text.tag_configure("bad", foreground=theme.WRONG_FG, background=theme.WRONG_BG)
        self.text.tag_configure("caret", background=theme.CARET, foreground=theme.BG)
        # Создан последним — значит, приоритетнее и "bad", и "caret": в строгом
        # режиме ошибка стоит под кареткой, и без этого тега её было не видно.
        self.text.tag_configure("caret_bad", background=theme.CARET_BAD, foreground=theme.BG)
        self.text.configure(state="disabled")

        self.result_var = tk.StringVar()
        self.result_label = tk.Label(wrap, textvariable=self.result_var, bg=theme.PANEL,
                                     fg=theme.GOOD, font=self.f_result)
        self.result_label.pack()

        # Плашка-уведомление: раскладка, Caps Lock, подтверждение сброса.
        # Кладётся через place поверх низа панели — появление и исчезновение
        # не двигает остальную раскладку.
        self.notice = tk.Label(wrap, font=self.f_chip, padx=self.px(12), pady=self.px(4))

    def _build_combo(self, parent: tk.Frame) -> None:
        self.combo_canvas = tk.Canvas(parent, height=self.density.combo_h, bg=theme.BG,
                                      highlightthickness=0)
        self.combo_canvas.pack(fill="x")
        c = self.combo_canvas
        self._combo_value = c.create_text(0, 0, text="0", fill=theme.TEXT_FAINT,
                                          font=self.f_combo, anchor="center")
        self._combo_caption = c.create_text(0, 0, text="КОМБО", fill=theme.TEXT_FAINT,
                                            font=self.f_caption, anchor="center")
        self._combo_bar_bg = c.create_rectangle(0, 0, 0, 0, fill=theme.PANEL, width=0)
        self._combo_bar = c.create_rectangle(0, 0, 0, 0, fill=theme.TEXT_FAINT, width=0)
        c.bind("<Configure>", self._on_combo_configure)

    def _build_keyboard(self, parent: tk.Frame) -> None:
        # Упаковывается позже, в _pack_keyboard: место в очереди pack должно
        # быть перед подсказками, иначе после F6 клавиатура уезжала под них.
        self.kb_holder = tk.Frame(parent, bg=theme.BG)
        self.kb_canvas = tk.Canvas(self.kb_holder, height=self.density.kb_h, bg=theme.BG,
                                   highlightthickness=0)
        self.kb_canvas.pack(fill="x")
        self.finger_var = tk.StringVar()
        tk.Label(self.kb_holder, textvariable=self.finger_var, bg=theme.BG,
                 fg=theme.TEXT_DIM, font=self.f_hint).pack(pady=(self.px(2), 0))
        self.kb_canvas.bind("<Configure>", self._on_kb_configure)

    def _build_footer(self, parent: tk.Frame) -> None:
        self.hint_var = tk.StringVar()
        self.footer_label = tk.Label(parent, textvariable=self.hint_var, bg=theme.BG,
                                     fg=theme.TEXT_FAINT, font=self.f_hint)
        self.footer_label.pack()
        self._refresh_hint()

    def _pack_keyboard(self) -> None:
        """Показать клавиатуру строго между комбо и строкой подсказок."""
        self.kb_holder.pack(fill="x", pady=(self.density.gap // 2, 0),
                            before=self.footer_label)

    def _build_help(self) -> None:
        self.help_frame = tk.Frame(self, bg=theme.PANEL_HI, highlightthickness=1,
                                   highlightbackground=theme.BORDER)
        side, row_pad = self.px(22), self.px(3)
        rows = (
            ("Esc", "пропустить фразу / закрыть справку"),
            ("Tab", "начать эту фразу заново"),
            ("F2", "язык: русский / английский"),
            ("F3", "режим тренировки"),
            ("F4 / Shift+F4", "ступень урока вперёд / назад"),
            ("F5", "строгий режим (не пускает дальше при ошибке)"),
            ("F6", "показать / скрыть экранную клавиатуру"),
            ("F7 дважды", "сбросить всю накопленную статистику"),
            ("F1", "закрыть эту справку"),
            ("Ctrl+Q", "выход"),
        )
        tk.Label(self.help_frame, text="Горячие клавиши", bg=theme.PANEL_HI,
                 fg=theme.TEXT, font=self.f_chip).grid(
                     row=0, column=0, columnspan=2, sticky="w", padx=side,
                     pady=(self.px(18), self.px(12)))
        for i, (key, what) in enumerate(rows, start=1):
            tk.Label(self.help_frame, text=key, bg=theme.PANEL_HI, fg=theme.ACCENT,
                     font=self.f_chip, anchor="e").grid(row=i, column=0, sticky="e",
                                                        padx=(side, self.px(12)), pady=row_pad)
            tk.Label(self.help_frame, text=what, bg=theme.PANEL_HI, fg=theme.TEXT_DIM,
                     font=self.f_hint, anchor="w").grid(row=i, column=1, sticky="w",
                                                        padx=(0, side), pady=row_pad)
        notes = ("«Ё» засчитывается и нажатием «Е».\n"
                 "После 5 секунд без нажатий время не идёт.")
        tk.Label(self.help_frame, text=notes, bg=theme.PANEL_HI, fg=theme.TEXT_FAINT,
                 font=self.f_hint, justify="left").grid(
                     row=len(rows) + 1, column=0, columnspan=2, sticky="w", padx=side,
                     pady=(self.px(12), self.px(16)))

    # ------------------------------------------------------- плотность / размер

    def _apply_density(self) -> None:
        """Применить размеры текущей плотности ко всем секциям."""
        d = self.density
        gap = d.gap
        self.f_target.configure(size=d.target)
        self.f_stat.configure(size=d.stat)
        self.f_combo.configure(size=d.combo)
        self.f_combo_big.configure(size=d.combo_big)
        self.f_result.configure(size=d.result)

        small = max(gap - 2, 2)
        self._header_bar.pack_configure(pady=(0, gap))
        self._session_label.pack_configure(pady=(0, small))
        self._stats_row.pack_configure(pady=(0, small))
        for value, cap in self._tile_parts:
            value.pack_configure(pady=(d.tile_pady, 0))
            cap.pack_configure(pady=(0, d.tile_pady))
        self.progress.pack_configure(pady=(0, gap + 2))
        self.text.configure(pady=d.text_pady, spacing1=d.line_above, spacing3=d.line_below)
        self.result_label.pack_configure(pady=(0, d.result_pady))
        self.combo_canvas.configure(height=d.combo_h)
        self.combo_canvas.pack_configure(pady=(gap, 0))
        self.kb_canvas.configure(height=d.kb_h)
        if self.kb_holder.winfo_manager():
            self.kb_holder.pack_configure(pady=(gap // 2, 0))
        self.footer_label.pack_configure(pady=(small, 0))

    @property
    def compact(self) -> bool:
        return self.density is self._compact

    def _set_density(self, density: Density) -> None:
        if density is self.density:
            return
        self.density = density
        self._apply_density()
        self._combo_tier = None      # пересобрать геометрию комбо под новую высоту
        self._rerender()             # другой кегль — другой перенос строк

    def _required_height(self, *, full_keyboard: bool = False) -> int:
        """Сколько пикселей по высоте просят все секции вместе с отступами.

        ``full_keyboard`` — посчитать так, будто клавиатура не ужата под
        нехватку места, а имеет штатную для плотности высоту.
        """
        total = 0
        for widget in self.body.pack_slaves():
            pady = widget.pack_info().get("pady", 0)
            # Tk отдаёт либо пару (сверху, снизу), либо одно число на обе стороны.
            pad = sum(map(int, pady)) if isinstance(pady, (tuple, list)) else 2 * int(pady)
            total += widget.winfo_reqheight() + pad
        if full_keyboard and self.kb_holder.winfo_manager():
            total += self.density.kb_h - self.kb_canvas.winfo_reqheight()
        return total

    def _check_fit(self) -> None:
        """Выбрать плотность так, чтобы всё влезало в окно по высоте.

        Обычная плотность предпочтительнее; компактная — когда без неё нижние
        секции (клавиатура, подсказки) срезались бы. Обратно в обычную
        переходим, только если она заведомо поместится, — без «дрожания».
        """
        avail = self.winfo_height() - 2 * self.px(BODY_PADY)
        if avail <= 1 or self._fitting:
            return
        # Смена плотности перерисовывает фразу, а перерисовка снова проверяет
        # размер — без этого флага они вызывали бы друг друга по кругу.
        self._fitting = True
        try:
            self._fit_density(avail)
        finally:
            self._fitting = False

    def _fit_density(self, avail: int) -> None:
        self.update_idletasks()
        if (self.compact
                and self._required_height(full_keyboard=True) + self._compact_saving <= avail):
            self._set_density(self._normal)
            self.update_idletasks()
        if not self.compact:
            need = self._required_height()
            if need <= avail:
                return
            self._set_density(self._compact)
            self.update_idletasks()
            self._compact_saving = max(need - self._required_height(), 0)
        # Компактно и всё равно тесно (длинная фраза в минимальном окне):
        # отдаём недостающее за счёт клавиатуры — клавиши масштабируются
        # по высоте холста и остаются целиком видны.
        over = self._required_height(full_keyboard=True) - avail
        kb_h = max(self.px(KB_MIN_H), self.density.kb_h - max(over, 0))
        if int(self.kb_canvas.cget("height")) != kb_h:
            self.kb_canvas.configure(height=kb_h)

    def _on_window_configure(self, event: tk.Event) -> None:
        # Привязка на корневом окне получает Configure и от всех потомков.
        if event.widget is not self:
            return
        size = (event.width, event.height)
        if size == self._win_size:
            return
        self._win_size = size
        if self._fit_id is not None:
            self.after_cancel(self._fit_id)
        self._fit_id = self.after(120, self._fit_job)

    def _fit_job(self) -> None:
        self._fit_id = None
        self._check_fit()

    # -------------------------------------------------------------- привязки

    def _bind_keys(self) -> None:
        self.bind("<KeyPress>", self._on_key)
        self.bind("<Escape>", self._on_escape)
        self.bind("<Tab>", lambda _e: self._action(self.restart_test))
        self.bind("<F1>", lambda _e: self._action(self.toggle_help))
        self.bind("<F2>", lambda _e: self._action(self.toggle_language))
        self.bind("<F3>", lambda _e: self._action(self.cycle_mode))
        self.bind("<F4>", lambda _e: self._action(self.next_stage))
        self.bind("<Shift-F4>", lambda _e: self._action(self.prev_stage))
        self.bind("<F5>", lambda _e: self._action(self.toggle_strict))
        self.bind("<F6>", lambda _e: self._action(self.toggle_keyboard))
        self.bind("<F7>", lambda _e: self._action(self.request_reset))
        self.bind("<Control-q>", lambda _e: self._quit())

    @staticmethod
    def _action(fn) -> str:
        """Выполнить команду и погасить событие, чтобы оно не попало в текст."""
        fn()
        return "break"

    def _on_escape(self, _event=None) -> str:
        """Esc закрывает справку, если она открыта, иначе пропускает фразу."""
        if self.help_open:
            self.toggle_help()
        else:
            self.new_test()
        return "break"

    def _on_key(self, event: tk.Event) -> str | None:
        if event.state & 0x4:  # Control — это команда, а не символ
            return None
        if self.help_open:
            return "break"     # справка модальна: печать в тест не уходит
        session = self.session
        if event.keysym == "BackSpace":
            if session is not None:
                self._apply(session.backspace())
            return "break"
        ch = event.char
        printable = bool(ch) and len(ch) == 1 and ch.isprintable()
        if session is not None and session.finished:
            # Итог висит до нажатия: печатный символ или Enter — следующая фраза.
            if printable or event.keysym in ("Return", "KP_Enter"):
                self.new_test()
                return "break"
            return None
        if not printable:
            return None
        if session is not None:
            self._check_input(ch, event.state)
            self._apply(session.type_char(ch))
        return "break"

    def _check_input(self, ch: str, state: int) -> None:
        """Предупредить, если нажатие испортила системная раскладка или Caps Lock.

        Само нажатие при этом всё равно засчитывается — как и любое другое.
        """
        session = self.session
        problem = input_problem(self.lang, ch, session.target[session.pos], state)
        if problem == WRONG_LAYOUT:
            self._show_notice(
                f"Включена другая раскладка — переключите на {LAYOUTS[self.lang].accusative}",
                "warn", INPUT_NOTICE_MS, source="input")
        elif problem == CAPS_LOCK:
            self._show_notice("Включён Caps Lock — выключите его", "warn",
                              INPUT_NOTICE_MS, source="input")
        elif self._notice_kind == "input":
            self._hide_notice()

    # ------------------------------------------------------------ жизненный цикл

    def new_test(self) -> None:
        """Собрать новую фразу и начать тест."""
        self._absorb_abandoned()
        self._stop_tick()
        self.source.lang, self.source.mode, self.source.stage = self.lang, self.mode, self.stage
        self._start_session(self.source.phrase(WORDS_PER_TEST, self.profile.weak_chars()))

    def restart_test(self) -> None:
        """Та же фраза заново — полезно, чтобы отработать сложное место."""
        if self.session is None:
            return
        self._absorb_abandoned()
        self._stop_tick()
        self._start_session(self.session.target)

    def _start_session(self, phrase: str) -> None:
        self.session = TypingSession(phrase, strict=self.strict,
                                     equivalents=EQUIVALENTS[self.lang])
        self._paused_shown = False
        self._stashed_result = None          # итог старой фразы не возвращаем
        if self._notice_kind == "input":
            self._hide_notice()
        self._render_target(phrase)
        self._place_caret()
        self._check_fit()            # фраза в 3+ строки может не влезть по высоте
        self.result_var.set("")
        self._refresh_stats(force=True)
        self._draw_combo()
        self._update_next_key()
        self._refresh_hint()

    def _record_key(self) -> str:
        """Рекорды раздельны по языку и режиму: урок на трёх буквах и обычный
        текст — разные дисциплины (A-14)."""
        return f"{self.lang}/{self.mode.value}"

    def _absorb_abandoned(self) -> None:
        """Брошенная фраза (Esc, Tab, смена режима, выход) не засчитывается как
        тест, но её ошибки остаются в статистике клавиш."""
        session = self.session
        if session is not None and session.started and not session.finished:
            self.profile.absorb_keys(session)

    def _render_target(self, phrase: str) -> None:
        """Полная отрисовка фразы — раз за тест и при смене ширины или кегля.

        Строки переносятся вручную и центрируются отступом ``lmargin1`` при
        выравнивании влево: при ``justify=center`` Tk растягивает фон первого
        символа строки до левого края, и каретка в начале строки
        превращалась в полосу.
        """
        t = self.text
        width = t.winfo_width()
        avail = width - 2 * int(t.cget("padx")) - 1
        measure = self.f_target.measure
        lines = wrap_words(phrase, avail, measure) if avail > 0 else [phrase]

        spans: list[tuple[str, str]] = []
        for row, line in enumerate(lines, start=1):
            spans.extend((f"{row}.{col}", f"{row}.{col + 1}") for col in range(len(line)))
        self._lines, self._spans = lines, spans
        self._caret_pos = None
        self._text_width = width

        t.configure(state="normal")
        t.delete("1.0", "end")
        t.insert("1.0", "\n".join(lines))
        t.tag_add("base", "1.0", "end")
        for row, line in enumerate(lines, start=1):
            margin = max((avail - measure(line.rstrip(" "))) // 2, 0) if avail > 0 else 0
            tag = f"line{row}"
            # lmargincolor обязателен: без него Tk заливает отступ фоном
            # первого символа строки — ошибкой или кареткой.
            t.tag_configure(tag, lmargin1=margin, lmargin2=margin, lmargincolor=theme.PANEL)
            t.tag_lower(tag)   # только отступ: цвета решают ok/bad/caret
            t.tag_add(tag, f"{row}.0", f"{row}.end")
        t.configure(state="disabled")
        self._fit_text_height()

    def _rerender(self) -> None:
        """Перерисовать текущую фразу с сохранением разметки (после ресайза)."""
        session = self.session
        if session is None:
            return
        self._render_target(session.target)
        for pos, mark in enumerate(session.marks):
            if mark is Mark.CORRECT:
                self.text.tag_add("ok", *self._spans[pos])
            elif mark is Mark.WRONG:
                self.text.tag_add("bad", *self._spans[pos])
        self._place_caret()

    def _place_caret(self) -> None:
        """Переставить каретку: снять тег ровно со старой позиции — O(1)."""
        if self._caret_pos is not None:
            self.text.tag_remove(self._caret_tag, *self._spans[self._caret_pos])
            self._caret_pos = None
        session = self.session
        if session is not None and not session.finished and session.pos < len(session.target):
            pos = session.pos
            # Строгий режим держит курсор на ошибке — показываем её красной
            # кареткой, иначе обычная каретка перекрывала красный фон.
            self._caret_tag = "caret_bad" if session.marks[pos] is Mark.WRONG else "caret"
            self.text.tag_add(self._caret_tag, *self._spans[pos])
            self._caret_pos = pos

    def _fit_text_height(self) -> None:
        """Подогнать высоту поля под реальное число строк.

        Иначе виджет держит фиксированную высоту и под короткой фразой
        остаётся полоса пустоты.
        """
        self.text.update_idletasks()
        try:
            # count -displaylines считает пересечённые границы строк, поэтому
            # до "end" — это ровно число экранных строк текста.
            lines = self.text.count("1.0", "end", "displaylines")
        except tk.TclError:
            return
        if isinstance(lines, tuple):
            lines = lines[0] if lines else None
        if lines:
            self.text.configure(height=max(1, min(int(lines), 8)))

    def _on_text_configure(self, event: tk.Event) -> None:
        # Перерисовываем только при смене ширины: изменение высоты — наших же
        # рук дело, и реагировать на него значило бы зациклиться.
        if event.width != self._text_width:
            self._rerender()

    def _apply(self, effect) -> None:
        """Отразить результат нажатия минимальным числом операций."""
        if not effect.accepted or self.session is None:
            return
        session = self.session

        # Перекрашиваем только изменившиеся позиции.
        for idx in effect.changed:
            start, end = self._spans[idx]
            mark = session.marks[idx]
            self.text.tag_remove("ok", start, end)
            self.text.tag_remove("bad", start, end)
            if mark is Mark.CORRECT:
                self.text.tag_add("ok", start, end)
            elif mark is Mark.WRONG:
                self.text.tag_add("bad", start, end)
        self._place_caret()

        if session.started and not session.finished:
            if self._paused_shown:           # вернулись после простоя
                self._paused_shown = False
                self._stashed_result = None
                self.result_var.set("")
            self._start_tick()               # уже идёт — ничего не делает
        if effect.combo_gained or effect.combo_broken:
            self._draw_combo(pulse=effect.combo_gained)
        self._update_next_key()

        if effect.finished:
            self._finish()
        else:
            # Полный пересчёт метрик делает таймер 5 раз в секунду; на каждое
            # нажатие двигаем только полоску прогресса — это один coords().
            self._update_progress()

    def _finish(self) -> None:
        """Завершение теста: метрики, профиль, итог висит до нажатия клавиши."""
        self._stop_tick()
        session = self.session
        if session is None:
            return
        metrics = session.metrics()
        new_record = self.profile.absorb(session, self._record_key())
        self._refresh_stats(force=True)

        parts = [f"{metrics.wpm:.0f} слов/мин", f"{metrics.accuracy:.0f}% точности"]
        if session.best_combo >= 10:
            parts.append(f"комбо ×{session.best_combo}")
        parts.append(count(metrics.errors, "ошибка", "ошибки", "ошибок")
                     if metrics.errors else "без ошибок")
        if new_record:
            parts.append("новый рекорд!")
        self.result_label.configure(
            fg=theme.accuracy_color(metrics.accuracy) if metrics.errors else theme.GOOD
        )
        self.result_var.set("  ·  ".join(parts))

        if (self.mode is Mode.LESSON and metrics.accuracy >= STAGE_UP_ACCURACY
                and self.stage < len(lesson_stages(self.lang)) - 1):
            self.stage += 1
            self._refresh_chips()
            self.result_var.set(self.result_var.get() + f"  →  {self.source.stage_title}")

        self._refresh_session_line()
        self._refresh_hint()
        self._persist()

    def _cancel_all_jobs(self) -> None:
        """Погасить всё отложенное. Иначе кадр анимации может выстрелить уже
        после уничтожения окна и Tk выругается «invalid command name»."""
        for attr in ("_tick_id", "_anim_id", "_resize_id", "_fit_id", "_notice_id"):
            job = getattr(self, attr)
            if job is not None:
                with suppress(tk.TclError):
                    self.after_cancel(job)
                setattr(self, attr, None)

    # ----------------------------------------------------------------- таймер

    def _start_tick(self) -> None:
        if self._tick_id is None:
            self._tick_id = self.after(TICK_MS, self._tick)

    def _stop_tick(self) -> None:
        if self._tick_id is not None:
            self.after_cancel(self._tick_id)
            self._tick_id = None

    def _tick(self) -> None:
        self._tick_id = None
        session = self.session
        if session is None or session.finished or not session.started:
            return  # тест не идёт — таймер не перезапускаем, очередь пустеет
        if session.is_idle():
            # Простой: время в движке уже стоит, тикать незачем. Таймер
            # проснётся со следующим нажатием (см. _apply).
            self._refresh_stats()
            self._paused_shown = True
            self.result_label.configure(fg=theme.TEXT_DIM)
            self.result_var.set("пауза — время не идёт, продолжайте печатать")
            return
        self._refresh_stats()
        self._tick_id = self.after(TICK_MS, self._tick)

    # ---------------------------------------------------------- уведомления

    def _show_notice(self, text: str, kind: str = "info", timeout_ms: int = INFO_NOTICE_MS,
                     *, source: str | None = None) -> None:
        """Показать плашку поверх низа панели с фразой; сама скроется."""
        style = (text, kind)
        if style != self._notice_style:
            bg, fg = NOTICE_COLORS[kind]
            self.notice.configure(text=text, bg=bg, fg=fg)
            self._notice_style = style
        self._notice_kind = source
        if self._stashed_result is None and self.result_var.get():
            # Плашка ложится на строку итога — убираем итог, пока она видна.
            self._stashed_result = (self.result_var.get(), self.result_label.cget("fg"))
            self.result_var.set("")
        if not self.notice_shown:
            self.notice.place(relx=0.5, rely=1.0, y=-self.px(6), anchor="s")
            self.notice_shown = True
        self.notice.lift()
        if self._notice_id is not None:
            self.after_cancel(self._notice_id)
        self._notice_id = self.after(timeout_ms, self._notice_expired)

    def _notice_expired(self) -> None:
        self._notice_id = None
        self._hide_notice()

    def _hide_notice(self) -> None:
        if self._notice_id is not None:
            self.after_cancel(self._notice_id)
            self._notice_id = None
        self.notice.place_forget()
        self.notice_shown = False
        self._notice_kind = None
        if self._stashed_result is not None:
            text, color = self._stashed_result
            self._stashed_result = None
            self.result_var.set(text)
            self.result_label.configure(fg=color)

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

    def _refresh_session_line(self) -> None:
        p = self.profile
        if p.tests == 0:
            self.session_var.set("")
            return
        self.session_var.set(
            f"Всего: {count(p.tests, 'тест', 'теста', 'тестов')} · {p.wpm:.0f} слов/мин · "
            f"{p.accuracy:.0f}% · лучшее комбо ×{p.best_combo}"
        )

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

    def _layout_keyboard(self) -> None:
        """Пересобрать клавиши. Вызывается только при смене размера или языка."""
        self._resize_id = None
        c = self.kb_canvas
        c.delete("all")
        self._kb_items.clear()
        self._hot_key = None

        layout = LAYOUTS[self.lang]
        rows = layout.display_rows
        width, height = c.winfo_width(), c.winfo_height()
        if width <= 1 or height <= 1:
            return
        longest = max(len(r) for r in rows)
        gap = self.px(4)
        kw = min(self.px(46), (width - self.px(40) - gap * longest) / longest)
        # Четыре ряда (три буквенных + пробел) обязаны уместиться по высоте:
        # раньше высота клавиш считалась только от ширины, и в низком окне
        # верхний ряд и пробел уходили за край холста.
        kh = min(self.px(34), kw, (height - 3 * gap - self.px(2)) / 4)
        if kw < self.px(12) or kh < self.px(10):
            return
        total_h = kh * 4 + gap * 3  # три ряда + пробел
        top = max((height - total_h) / 2, 0)

        for r, row in enumerate(rows):
            row_w = len(row) * (kw + gap) - gap
            x0 = (width - row_w) / 2
            y0 = top + r * (kh + gap)
            for i, ch in enumerate(row):
                x = x0 + i * (kw + gap)
                base_bg = theme.KEY_HOME_BG if ch in layout.anchors else theme.KEY_BG
                rect = c.create_rectangle(x, y0, x + kw, y0 + kh, fill=base_bg, width=0)
                label = c.create_text(x + kw / 2, y0 + kh / 2, text=ch.upper(),
                                      fill=theme.KEY_FG, font=self.f_key)
                self._kb_items[ch] = (rect, label)

        # Пробел отдельным широким блоком.
        sw = kw * 7
        x = (width - sw) / 2
        y = top + 3 * (kh + gap)
        rect = c.create_rectangle(x, y, x + sw, y + kh, fill=theme.KEY_BG, width=0)
        label = c.create_text(x + sw / 2, y + kh / 2, text="ПРОБЕЛ",
                              fill=theme.KEY_FG, font=self.f_key)
        self._kb_items[" "] = (rect, label)
        self._update_next_key()

    def _update_next_key(self) -> None:
        """Подсветить следующую клавишу: два itemconfigure, без перерисовки."""
        if not self.show_keyboard or not self._kb_items:
            return
        session = self.session
        nxt = None
        if session and not session.finished and session.pos < len(session.target):
            nxt = session.target[session.pos].lower()

        if nxt == self._hot_key:
            return
        layout = LAYOUTS[self.lang]
        if self._hot_key is not None and self._hot_key in self._kb_items:
            rect, label = self._kb_items[self._hot_key]
            base_bg = theme.KEY_HOME_BG if self._hot_key in layout.anchors else theme.KEY_BG
            self.kb_canvas.itemconfigure(rect, fill=base_bg)
            self.kb_canvas.itemconfigure(label, fill=theme.KEY_FG)
        self._hot_key = nxt
        if nxt and nxt in self._kb_items:
            rect, label = self._kb_items[nxt]
            self.kb_canvas.itemconfigure(rect, fill=theme.KEY_NEXT_BG)
            self.kb_canvas.itemconfigure(label, fill=theme.KEY_NEXT_FG)
            finger = finger_for(self.lang, nxt)
            hint = FINGER_NAMES[finger] if finger is not None else ""
            alternative = EQUIVALENTS[self.lang].get(nxt)
            if hint and alternative:
                hint += f" · можно и «{alternative}»"
            self.finger_var.set(hint)
        else:
            self.finger_var.set("")

    # ---------------------------------------------------------------- команды

    def toggle_language(self) -> None:
        self.lang = "en" if self.lang == "ru" else "ru"
        self.stage = min(self.stage, len(lesson_stages(self.lang)) - 1)
        self._refresh_chips()
        self._layout_keyboard()
        self.new_test()

    def cycle_mode(self) -> None:
        self.mode = MODE_ORDER[(MODE_ORDER.index(self.mode) + 1) % len(MODE_ORDER)]
        self._refresh_chips()
        self.new_test()

    def next_stage(self) -> None:
        self._step_stage(+1)

    def prev_stage(self) -> None:
        self._step_stage(-1)

    def _step_stage(self, step: int) -> None:
        """F4 вне уроков открывает уроки на текущей ступени; внутри — листает
        ступени, не перескакивая с последней на первую."""
        if self.mode is not Mode.LESSON:
            self.mode = Mode.LESSON
        else:
            target = self.stage + step
            if not 0 <= target < len(lesson_stages(self.lang)):
                self._show_notice("Это последняя ступень" if step > 0 else "Это первая ступень")
                return
            self.stage = target
        self._refresh_chips()
        self.new_test()

    def toggle_strict(self) -> None:
        self.strict = not self.strict
        self._refresh_hint()
        self.restart_test()

    def toggle_keyboard(self) -> None:
        self.show_keyboard = not self.show_keyboard
        if self.show_keyboard:
            self._pack_keyboard()
            self._layout_keyboard()
        else:
            self.kb_holder.pack_forget()
        self._refresh_hint()
        # Без клавиатуры может хватить обычной плотности: прежняя оценка
        # экономии учитывала клавиатуру, поэтому сбрасываем её.
        self._compact_saving = 0
        self._check_fit()

    def toggle_help(self) -> None:
        self.help_open = not self.help_open
        if self.help_open:
            self.help_frame.place(relx=0.5, rely=0.5, anchor="center")
            self.help_frame.lift()
        else:
            self.help_frame.place_forget()

    def request_reset(self) -> None:
        """Сброс всей статистики — только по второму F7 в течение 3 секунд."""
        now = time.monotonic()
        if now < self._reset_armed_until:
            self._reset_armed_until = 0.0
            self.reset_stats()
            self._show_notice("Статистика сброшена")
        else:
            self._reset_armed_until = now + RESET_CONFIRM_MS / 1000
            self._show_notice("Сбросить всю статистику? Нажмите F7 ещё раз",
                              "danger", RESET_CONFIRM_MS)

    def reset_stats(self) -> None:
        self.profile = Profile()
        self._refresh_session_line()
        self._refresh_stats(force=True)
        self._persist()

    def _refresh_chips(self) -> None:
        self.lang_var.set("РУССКИЙ" if self.lang == "ru" else "ENGLISH")
        self.mode_var.set(self.mode.title.upper())
        stages = lesson_stages(self.lang)
        idx = min(self.stage, len(stages) - 1)
        self.stage_var.set(f"УРОК {idx + 1}/{len(stages)} · {stages[idx][0]}")
        if len(self._chips) == 3:
            # Ступень имеет смысл только в режиме уроков: вне их чип скрыт, а
            # не приглушён — клик по приглушённому молча менял режим.
            chip = self._chips[2]
            in_lesson = self.mode is Mode.LESSON
            if in_lesson and not chip.winfo_manager():
                chip.pack(side="left", padx=(0, self.px(8)))
            elif not in_lesson and chip.winfo_manager():
                chip.pack_forget()
        self.source.lang, self.source.mode, self.source.stage = self.lang, self.mode, self.stage
        self._refresh_session_line()

    def _refresh_hint(self) -> None:
        session = self.session
        if session is not None and session.finished:
            bits = ["любая клавиша — дальше", "Tab — ещё раз", "F1 — справка"]
        else:
            bits = ["Esc — дальше", "Tab — заново", "F1 — справка"]
        if self.strict:
            bits.append("строгий режим включён")
        if not self.show_keyboard:
            bits.append("клавиатура скрыта (F6)")
        self.hint_var.set("     ".join(bits))

    # ------------------------------------------------------------------ прочее

    def _persist(self) -> None:
        save_profile(self.profile, {
            "lang": self.lang,
            "mode": self.mode.value,
            "stage": self.stage,
            "strict": self.strict,
            "show_keyboard": self.show_keyboard,
        })

    def _quit(self) -> None:
        self._absorb_abandoned()  # ошибки недобранной фразы — в статистику клавиш
        self._persist()
        self.destroy()

    def destroy(self) -> None:
        # Любой путь закрытия окна проходит здесь, включая крестик и тесты.
        self._cancel_all_jobs()
        super().destroy()

    def run(self) -> None:
        self.mainloop()


def main() -> int:
    app = TypingApp()
    app.run()
    return 0
