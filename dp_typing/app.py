"""Интерфейс тренажёра на tkinter.

Устройство и причины решений по производительности:

* отдельного поля ввода нет — нажатия ловятся привязкой на корневом окне,
  поэтому нечего синхронизировать между виджетами;
* целевой текст живёт в ``tk.Text`` и рисуется один раз за тест; на каждое
  нажатие перекрашиваются 2-3 позиции через теги, а не вся строка;
* пока тест не идёт, в очереди нет ни одного ``after`` — приложение в покое
  не потребляет процессор вообще;
* пока тест идёт, работает ровно один таймер на 200 мс (обновление метрик);
* анимация комбо — одна самозавершающаяся цепочка кадров с заранее
  просчитанным градиентом, меняется цвет двух элементов Canvas без
  пересборки layout;
* каретка не мигает (``insertofftime=0``), что убирает периодическую
  перерисовку, которую Tk устраивает сам по себе.
"""

from __future__ import annotations

import random
import tkinter as tk
from contextlib import suppress
from dataclasses import dataclass
from tkinter import font as tkfont

from . import __version__, theme
from .engine import Mark, Profile, TypingSession
from .layout import FINGER_NAMES, LAYOUTS, finger_for
from .storage import load as load_profile
from .storage import restore as restore_profile
from .storage import save as save_profile
from .words import Mode, TextSource, lesson_stages

#: Период обновления метрик во время теста, мс.
TICK_MS = 200
#: Пауза перед следующим тестом после финиша, мс.
NEXT_TEST_MS = 1500
#: Кадры анимации комбо и шаг между ними.
ANIM_FRAMES = 8
ANIM_STEP_MS = 28
#: Слов во фразе.
WORDS_PER_TEST = 9
#: Точность, с которой урок повышает ступень.
STAGE_UP_ACCURACY = 96.0

MODE_ORDER = (Mode.LESSON, Mode.COMMON, Mode.PSEUDO, Mode.ADAPTIVE)

#: Внешний отступ основной колонки по вертикали.
BODY_PADY = 14


@dataclass(frozen=True)
class Density:
    """Размеры интерфейса. Компактная плотность включается, когда содержимое
    не помещается в окно по высоте (маленькое окно или фраза в 3+ строки)."""

    target: int          # кегль фразы
    stat: int            # кегль чисел в плитках
    combo: int
    combo_big: int
    result: int
    combo_h: int         # высота холста комбо
    kb_h: int            # высота холста клавиатуры
    text_pady: int
    line_above: int      # spacing1 у Text: воздух над строкой
    line_below: int      # spacing3 у Text: воздух под строкой
    result_pady: int
    tile_pady: int
    gap: int             # базовый вертикальный зазор между секциями


NORMAL = Density(target=22, stat=21, combo=26, combo_big=31, result=13,
                 combo_h=74, kb_h=150, text_pady=24, line_above=6, line_below=10,
                 result_pady=16, tile_pady=10, gap=12)
COMPACT = Density(target=18, stat=16, combo=20, combo_big=24, result=12,
                  combo_h=56, kb_h=100, text_pady=12, line_above=3, line_below=6,
                  result_pady=8, tile_pady=5, gap=5)

#: Ниже этой высоты холста клавиши стали бы нечитаемыми (4 ряда по ~13 px).
KB_MIN_H = 64


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
        self.title(f"DP Typing Master {__version__}")
        self.configure(bg=theme.BG)
        self.geometry("1040x720")
        self.minsize(760, 560)

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
        self._next_id: str | None = None
        self._anim_id: str | None = None
        self._resize_id: str | None = None
        self._fit_id: str | None = None
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
        self._combo_h = NORMAL.combo_h
        self._progress_w = 0
        self._caret_pos: int | None = None
        # Тег каретки: обычный или «ошибка под кареткой» (строгий режим).
        self._caret_tag = "caret"
        # Плотность интерфейса и оценка, сколько пикселей экономит компактная.
        self.density = NORMAL
        self._compact_saving = 0
        self._win_size = (0, 0)
        self._text_width = 0
        self._combo_tier = None
        self._pulsed_tier = None
        self._combo_bar_right = -1

        self._build_fonts()
        self._build_ui()
        self._bind_keys()

        self.protocol("WM_DELETE_WINDOW", self._quit)
        self.bind("<Configure>", self._on_window_configure)
        # Фокус на само окно: клавиши ловит корневая привязка,
        # отдельного поля ввода в приложении нет.
        self.focus_set()
        self.new_test()

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
        self.body.pack(fill="both", expand=True, padx=18, pady=BODY_PADY)
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
        chips.pack(side="left", padx=(18, 0))
        self.lang_var = tk.StringVar()
        self.mode_var = tk.StringVar()
        self.stage_var = tk.StringVar()
        self._chips: list[tk.Label] = []
        for var, cmd in ((self.lang_var, self.toggle_language),
                         (self.mode_var, self.cycle_mode),
                         (self.stage_var, self.next_stage)):
            chip = tk.Label(chips, textvariable=var, bg=theme.PANEL, fg=theme.TEXT_DIM,
                            font=self.f_chip, padx=10, pady=4, cursor="hand2")
            chip.pack(side="left", padx=(0, 8))
            chip.bind("<Button-1>", lambda _e, c=cmd: c())
            self._chips.append(chip)

        # Итоги сессии — отдельной строкой: в один ряд с чипами они не влезали
        # и обрезали название ступени.
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
        self._tile_parts: list[tuple[tk.Label, tk.Label]] = []
        for key, caption in (("wpm", "СЛОВ/МИН"), ("cpm", "ЗНАКОВ/МИН"),
                             ("acc", "ТОЧНОСТЬ"), ("err", "ОШИБКИ"),
                             ("best", "РЕКОРД WPM")):
            tile = tk.Frame(row, bg=theme.PANEL)
            tile.pack(side="left", fill="x", expand=True, padx=(0, 8))
            var = tk.StringVar(value="0")
            value = tk.Label(tile, textvariable=var, bg=theme.PANEL, fg=theme.TEXT,
                             font=self.f_stat, anchor="w")
            value.pack(fill="x", padx=14)
            cap = tk.Label(tile, text=caption, bg=theme.PANEL, fg=theme.TEXT_FAINT,
                           font=self.f_caption, anchor="w")
            cap.pack(fill="x", padx=14)
            self.stat_vars[key] = var
            self.stat_labels[key] = value
            self._tile_parts.append((value, cap))

        self.progress = tk.Canvas(parent, height=3, bg=theme.PANEL, highlightthickness=0)
        self.progress.pack(fill="x")
        self._progress_bar = self.progress.create_rectangle(
            0, 0, 0, 3, fill=theme.ACCENT, width=0
        )
        self.progress.bind("<Configure>", self._on_progress_configure)

    def _build_text(self, parent: tk.Frame) -> None:
        # fill="x" (а не "both"): панель берёт высоту по содержимому и
        # центрируется в свободном месте, вместо пустого поля во весь экран.
        wrap = tk.Frame(parent, bg=theme.PANEL)
        wrap.pack(fill="x", expand=True)

        self.text = tk.Text(
            wrap, bg=theme.PANEL, fg=theme.PENDING, font=self.f_target,
            wrap="word", relief="flat", highlightthickness=0, borderwidth=0,
            padx=28, pady=self.density.text_pady, spacing1=self.density.line_above,
            spacing3=self.density.line_below, cursor="arrow",
            insertofftime=0, insertwidth=0, takefocus=0,
            # Text по умолчанию просит 24 строки — при кегле 22 это выше всего
            # окна, и pack не оставил бы места клавиатуре. Просим минимум,
            # а реальную высоту виджет получает через expand=True.
            width=1, height=4,
        )
        # fill="x" + expand=True центрирует блок текста по вертикали,
        # вместо того чтобы растягивать пустую панель на всю высоту.
        self.text.pack(fill="x")
        self.text.bind("<Configure>", self._on_text_configure)
        self.text.tag_configure("base", justify="center", foreground=theme.PENDING)
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

    def _build_combo(self, parent: tk.Frame) -> None:
        self.combo_canvas = tk.Canvas(parent, height=self.density.combo_h, bg=theme.BG,
                                      highlightthickness=0)
        self.combo_canvas.pack(fill="x")
        c = self.combo_canvas
        self._combo_value = c.create_text(0, 26, text="0", fill=theme.TEXT_FAINT,
                                          font=self.f_combo, anchor="center")
        self._combo_caption = c.create_text(0, 50, text="КОМБО", fill=theme.TEXT_FAINT,
                                            font=self.f_caption, anchor="center")
        self._combo_bar_bg = c.create_rectangle(0, 64, 0, 67, fill=theme.PANEL, width=0)
        self._combo_bar = c.create_rectangle(0, 64, 0, 67, fill=theme.TEXT_FAINT, width=0)
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
                 fg=theme.TEXT_DIM, font=self.f_hint).pack(pady=(2, 0))
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

        self._header_bar.pack_configure(pady=(0, gap))
        self._session_label.pack_configure(pady=(0, max(gap - 2, 2)))
        self._stats_row.pack_configure(pady=(0, max(gap - 2, 2)))
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
        self.footer_label.pack_configure(pady=(max(gap - 2, 2), 0))

    @property
    def compact(self) -> bool:
        return self.density is COMPACT

    def _set_density(self, density: Density) -> None:
        if density is self.density:
            return
        self.density = density
        self._apply_density()
        self._combo_tier = None      # пересобрать геометрию комбо под новую высоту
        self._fit_text_height()      # другой кегль — другое число строк

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
        avail = self.winfo_height() - 2 * BODY_PADY
        if avail <= 1:
            return
        self.update_idletasks()
        if (self.compact
                and self._required_height(full_keyboard=True) + self._compact_saving <= avail):
            self._set_density(NORMAL)
            self.update_idletasks()
        if not self.compact:
            need = self._required_height()
            if need <= avail:
                return
            self._set_density(COMPACT)
            self.update_idletasks()
            self._compact_saving = max(need - self._required_height(), 0)
        # Компактно и всё равно тесно (длинная фраза в минимальном окне):
        # отдаём недостающее за счёт клавиатуры — клавиши масштабируются
        # по высоте холста и остаются целиком видны.
        over = self._required_height(full_keyboard=True) - avail
        kb_h = max(KB_MIN_H, self.density.kb_h - max(over, 0))
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

    def _build_help(self) -> None:
        self.help_frame = tk.Frame(self, bg=theme.PANEL_HI, highlightthickness=1,
                                   highlightbackground=theme.BORDER)
        rows = (
            ("Esc", "пропустить фразу"),
            ("Tab", "начать эту фразу заново"),
            ("F2", "язык: русский / английский"),
            ("F3", "режим тренировки"),
            ("F4 / Shift+F4", "ступень урока вперёд / назад"),
            ("F5", "строгий режим (не пускает дальше при ошибке)"),
            ("F6", "показать / скрыть экранную клавиатуру"),
            ("F7", "сбросить накопленную статистику"),
            ("F1", "закрыть эту справку"),
            ("Ctrl+Q", "выход"),
        )
        tk.Label(self.help_frame, text="Горячие клавиши", bg=theme.PANEL_HI,
                 fg=theme.TEXT, font=self.f_chip).grid(
                     row=0, column=0, columnspan=2, sticky="w", padx=22, pady=(18, 12))
        for i, (key, what) in enumerate(rows, start=1):
            tk.Label(self.help_frame, text=key, bg=theme.PANEL_HI, fg=theme.ACCENT,
                     font=self.f_chip, anchor="e").grid(row=i, column=0, sticky="e",
                                                        padx=(22, 12), pady=3)
            tk.Label(self.help_frame, text=what, bg=theme.PANEL_HI, fg=theme.TEXT_DIM,
                     font=self.f_hint, anchor="w").grid(row=i, column=1, sticky="w",
                                                        padx=(0, 22), pady=3)
        tk.Frame(self.help_frame, bg=theme.PANEL_HI, height=14).grid(row=len(rows) + 1,
                                                                     column=0)

    # -------------------------------------------------------------- привязки

    def _bind_keys(self) -> None:
        self.bind("<KeyPress>", self._on_key)
        self.bind("<Escape>", lambda _e: self._action(self.new_test))
        self.bind("<Tab>", lambda _e: self._action(self.restart_test))
        self.bind("<F1>", lambda _e: self._action(self.toggle_help))
        self.bind("<F2>", lambda _e: self._action(self.toggle_language))
        self.bind("<F3>", lambda _e: self._action(self.cycle_mode))
        self.bind("<F4>", lambda _e: self._action(self.next_stage))
        self.bind("<Shift-F4>", lambda _e: self._action(self.prev_stage))
        self.bind("<F5>", lambda _e: self._action(self.toggle_strict))
        self.bind("<F6>", lambda _e: self._action(self.toggle_keyboard))
        self.bind("<F7>", lambda _e: self._action(self.reset_stats))
        self.bind("<Control-q>", lambda _e: self._quit())

    @staticmethod
    def _action(fn) -> str:
        """Выполнить команду и погасить событие, чтобы оно не попало в текст."""
        fn()
        return "break"

    def _on_key(self, event: tk.Event) -> str | None:
        if event.state & 0x4:  # Control — это команда, а не символ
            return None
        ch = event.char
        if event.keysym == "BackSpace":
            if self.session is not None:
                self._apply(self.session.backspace())
            return "break"
        if not ch or len(ch) != 1 or not ch.isprintable():
            return None
        # Досрочный переход к следующей фразе, если ждём таймер финиша.
        if self._next_id is not None:
            self._cancel_next()
            self.new_test()
            return "break"
        if self.session is not None:
            self._apply(self.session.type_char(ch))
        return "break"

    # ------------------------------------------------------------ жизненный цикл

    def new_test(self) -> None:
        """Собрать новую фразу и начать тест."""
        self._cancel_next()
        self._stop_tick()
        self.source.lang, self.source.mode, self.source.stage = self.lang, self.mode, self.stage
        phrase = self.source.phrase(WORDS_PER_TEST, self.profile.weak_chars())
        self.session = TypingSession(phrase, strict=self.strict)
        self._render_target(phrase)
        self.result_var.set("")
        self._refresh_stats(force=True)
        self._draw_combo()
        self._update_next_key()

    def restart_test(self) -> None:
        """Та же фраза заново — полезно, чтобы отработать сложное место."""
        if self.session is None:
            return
        self._cancel_next()
        self._stop_tick()
        phrase = self.session.target
        self.session = TypingSession(phrase, strict=self.strict)
        self._render_target(phrase)
        self.result_var.set("")
        self._refresh_stats(force=True)
        self._draw_combo()
        self._update_next_key()

    def _render_target(self, phrase: str) -> None:
        """Полная отрисовка целевого текста — единственный раз за тест."""
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", phrase)
        self.text.tag_add("base", "1.0", "end")
        self.text.tag_add("caret", "1.0", "1.1")
        self.text.configure(state="disabled")
        self._caret_pos = 0
        self._caret_tag = "caret"
        self._fit_text_height()
        # Фраза в 3+ строки может не влезть даже в окно обычного размера.
        self._check_fit()

    def _fit_text_height(self) -> None:
        """Подогнать высоту поля под реальное число строк после переноса.

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
            self._text_width = self.text.winfo_width()
            self.text.configure(height=max(1, min(int(lines), 8)))

    def _on_text_configure(self, event: tk.Event) -> None:
        # Пересчитываем только при смене ширины: изменение высоты — наших же
        # рук дело, и реагировать на него значило бы зациклиться.
        if event.width != self._text_width:
            self._text_width = event.width
            self._fit_text_height()

    def _apply(self, effect) -> None:
        """Отразить результат нажатия минимальным числом операций."""
        if not effect.accepted or self.session is None:
            return
        session = self.session

        # Перекрашиваем только изменившиеся позиции.
        for idx in effect.changed:
            start, end = f"1.{idx}", f"1.{idx + 1}"
            mark = session.marks[idx]
            self.text.tag_remove("ok", start, end)
            self.text.tag_remove("bad", start, end)
            if mark is Mark.CORRECT:
                self.text.tag_add("ok", start, end)
            elif mark is Mark.WRONG:
                self.text.tag_add("bad", start, end)

        # Каретка: снимаем тег ровно со старой позиции. Проход по всей строке
        # здесь делал стоимость нажатия линейной от длины фразы.
        if self._caret_pos is not None:
            old = self._caret_pos
            self.text.tag_remove(self._caret_tag, f"1.{old}", f"1.{old + 1}")
            self._caret_pos = None
        if not effect.finished and session.pos < len(session.target):
            pos = session.pos
            # Строгий режим держит курсор на ошибке — показываем её красной
            # кареткой, иначе обычная каретка перекрывала красный фон.
            self._caret_tag = "caret_bad" if session.marks[pos] is Mark.WRONG else "caret"
            self.text.tag_add(self._caret_tag, f"1.{pos}", f"1.{pos + 1}")
            self._caret_pos = pos

        if effect.started:
            self._start_tick()
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
        """Завершение теста: метрики, профиль, автопереход ровно один раз."""
        self._stop_tick()
        session = self.session
        if session is None:
            return
        metrics = session.metrics()
        self.profile.absorb(session)
        self._refresh_stats(force=True)

        parts = [f"{metrics.wpm:.0f} слов/мин", f"{metrics.accuracy:.0f}% точности"]
        if session.best_combo >= 10:
            parts.append(f"комбо ×{session.best_combo}")
        parts.append(f"{metrics.errors} ошиб." if metrics.errors else "без ошибок")
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
        self._persist()
        # Единственный запланированный переход: id хранится и гасится при
        # любом досрочном действии, поэтому два таймера одновременно невозможны.
        self._next_id = self.after(NEXT_TEST_MS, self._auto_next)

    def _auto_next(self) -> None:
        self._next_id = None
        self.new_test()

    def _cancel_next(self) -> None:
        if self._next_id is not None:
            self.after_cancel(self._next_id)
            self._next_id = None

    def _cancel_all_jobs(self) -> None:
        """Погасить всё отложенное. Иначе кадр анимации может выстрелить уже
        после уничтожения окна и Tk выругается «invalid command name»."""
        for attr in ("_tick_id", "_next_id", "_anim_id", "_resize_id", "_fit_id"):
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
        self._refresh_stats()
        self._tick_id = self.after(TICK_MS, self._tick)

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
            "best": f"{max(self.profile.best_wpm, m.wpm if session.finished else 0):.0f}",
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
            self.progress.coords(self._progress_bar, 0, 0, filled, 3)

    def _refresh_session_line(self) -> None:
        p = self.profile
        if p.tests == 0:
            self.session_var.set("")
            return
        self.session_var.set(
            f"{p.tests} тест. · {p.wpm:.0f} слов/мин · {p.accuracy:.0f}% · "
            f"лучшее комбо ×{p.best_combo}"
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
        return round(h * 0.35), round(h * 0.68), h - 10

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

        # Тяжёлая часть — подписи и позиции — трогается только когда сменился
        # уровень комбо или размер окна, а не на каждое нажатие.
        if tier is not self._combo_tier:
            self._combo_tier = tier
            c.coords(self._combo_value, mid, value_y)
            c.coords(self._combo_caption, mid, caption_y)
            caption = f"КОМБО · {tier.name.upper()}" if tier.name else "КОМБО"
            c.itemconfigure(self._combo_caption, text=caption, fill=tier.color)
            c.itemconfigure(self._combo_bar, fill=tier.color)
            bar_w = min(320, width - 80)
            c.coords(self._combo_bar_bg, mid - bar_w // 2, bar_y,
                     mid - bar_w // 2 + bar_w, bar_y + 3)

        c.itemconfigure(self._combo_value, text=f"×{combo}" if combo else "—")

        bar_w = min(320, width - 80)
        left = mid - bar_w // 2
        nxt = theme.next_threshold(combo)
        filled = 1.0 if nxt is None else (combo - tier.threshold) / max(nxt - tier.threshold, 1)
        right = round(left + bar_w * filled)
        if right != self._combo_bar_right:      # меньше пикселя — не дёргаем Tk
            self._combo_bar_right = right
            c.coords(self._combo_bar, left, bar_y, right, bar_y + 3)

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
        """Пересобрать клавиши. Вызывается только при смене ширины или языка."""
        self._resize_id = None
        c = self.kb_canvas
        c.delete("all")
        self._kb_items.clear()
        self._hot_key = None

        layout = LAYOUTS[self.lang]
        rows = layout.rows
        width, height = c.winfo_width(), c.winfo_height()
        if width <= 1 or height <= 1:
            return
        longest = max(len(r) for r in rows)
        gap = 4
        kw = min(46, (width - 40 - gap * longest) / longest)
        # Четыре ряда (три буквенных + пробел) обязаны уместиться по высоте:
        # раньше высота клавиш считалась только от ширины, и в низком окне
        # верхний ряд и пробел уходили за край холста.
        kh = min(34, kw, (height - 3 * gap - 2) / 4)
        if kw < 12 or kh < 10:
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
            self.finger_var.set(FINGER_NAMES[finger] if finger is not None else "")
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
        self.stage = (self.stage + 1) % len(lesson_stages(self.lang))
        self.mode = Mode.LESSON
        self._refresh_chips()
        self.new_test()

    def prev_stage(self) -> None:
        self.stage = (self.stage - 1) % len(lesson_stages(self.lang))
        self.mode = Mode.LESSON
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
        if self.help_frame.winfo_ismapped():
            self.help_frame.place_forget()
        else:
            self.help_frame.place(relx=0.5, rely=0.5, anchor="center")

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
            # Ступень имеет смысл только в режиме уроков.
            in_lesson = self.mode is Mode.LESSON
            self._chips[2].configure(fg=theme.TEXT_DIM if in_lesson else theme.TEXT_FAINT,
                                     bg=theme.PANEL if in_lesson else theme.BG)
        self.source.lang, self.source.mode, self.source.stage = self.lang, self.mode, self.stage
        self._refresh_session_line()

    def _refresh_hint(self) -> None:
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
        if self.session is not None and not self.session.finished:
            self.profile.absorb(self.session)  # не терять недобранный тест
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
