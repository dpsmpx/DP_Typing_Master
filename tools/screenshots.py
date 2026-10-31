"""Снять скриншоты основных экранов для документации.

Запускает настоящее окно, «печатает» в нём с правдоподобным темпом и
сохраняет PNG. Нужны X-сервер (обычно Xvfb) и ImageMagick (`import`):

    xvfb-run -a -s "-screen 0 1280x900x24" python tools/screenshots.py docs/screenshots

Личный профиль не трогается: конфиг уводится во временный каталог.
"""

from __future__ import annotations

import os
import random
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="dp-typing-shots-")

from dp_typing import app as app_module  # noqa: E402
from dp_typing.engine import TypingSession  # noqa: E402
from dp_typing.words import Mode  # noqa: E402


class VirtualClock:
    """Часы, которые идут только когда «нажимают» клавишу."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


CLOCK = VirtualClock()
PACE = random.Random(7)
# Сессии приложения получают виртуальные часы — иначе программный ввод
# мгновенный и скорость упиралась бы в потолок 1500 знаков/мин.
app_module.TypingSession = lambda target, strict=False: TypingSession(
    target, strict=strict, clock=CLOCK
)


def settle(win, ms: int = 350) -> None:
    deadline = time.time() + ms / 1000
    while time.time() < deadline:
        win.update()
        time.sleep(0.005)


def press(win, ch: str) -> None:
    CLOCK.now += max(0.07, PACE.gauss(0.165, 0.045))   # ~70 слов/мин
    win._on_key(type("Event", (), {"char": ch, "keysym": "a", "state": 0})())
    win.update()


def wrong_for(ch: str) -> str:
    pool = "фывапролджэ" if ord(ch) > 127 else "asdfghjkl"
    return next(c for c in pool if c != ch)


def type_chars(win, count: int, errors_at: frozenset[int] = frozenset()) -> None:
    session = win.session
    for i in range(count):
        if session.finished:
            break
        expected = session.target[session.pos]
        press(win, wrong_for(expected) if i in errors_at else expected)


def finish(win, errors_at: frozenset[int] = frozenset()) -> None:
    type_chars(win, len(win.session.target), errors_at)
    win._cancel_next()          # не уходить на следующую фразу во время съёмки


def shot(win, out: Path, name: str) -> None:
    win._refresh_stats(force=True)
    settle(win)
    x, y = win.winfo_rootx(), win.winfo_rooty()
    w, h = win.winfo_width(), win.winfo_height()
    path = out / f"{name}.png"
    subprocess.run(["import", "-window", "root", "-crop", f"{w}x{h}+{x}+{y}",
                    "+repage", str(path)], check=True)
    print(f"{path}  {w}x{h}")


def main(out: Path) -> int:
    if shutil.which("import") is None:
        print("нужен ImageMagick (команда import)", file=sys.stderr)
        return 1
    out.mkdir(parents=True, exist_ok=True)

    win = app_module.TypingApp()
    win.geometry("1040x720+0+0")
    win.rng.seed(11)
    win.new_test()
    settle(win, 600)
    shot(win, out, "01_start")

    type_chars(win, 34, frozenset({5}))
    shot(win, out, "02_typing")

    finish(win, frozenset({9}))
    shot(win, out, "03_result")

    for errors in ({3, 17, 30}, {12, 26}):      # накопить статистику клавиш
        win.new_test()
        finish(win, frozenset(errors))

    win.mode, win.stage = Mode.LESSON, 1
    win._refresh_chips()
    win.new_test()
    finish(win)                                  # 100% → ступень повышается
    shot(win, out, "04_lesson")

    win.mode = Mode.ADAPTIVE
    win._refresh_chips()
    win.new_test()
    type_chars(win, 12)
    shot(win, out, "05_adaptive")

    win.toggle_language()
    win.mode = Mode.PSEUDO
    win._refresh_chips()
    win.new_test()
    settle(win, 400)
    type_chars(win, 18, frozenset({8}))
    shot(win, out, "06_english_pseudo")

    win.toggle_help()
    shot(win, out, "07_help")
    win.toggle_help()

    win.toggle_language()
    win.mode = Mode.COMMON
    win._refresh_chips()
    win.geometry("760x560+0+0")
    settle(win, 500)
    win.new_test()
    settle(win, 300)
    type_chars(win, 20, frozenset({14}))
    shot(win, out, "08_compact")

    win.destroy()
    return 0


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "screenshots"
    raise SystemExit(main(target))
