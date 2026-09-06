#!/usr/bin/env python3
"""Точка входа DP Typing Master.

Файл намеренно оставлен на прежнем месте и под прежним именем, чтобы
работал привычный запуск ``python DP_Typing_Master.py``. Вся реализация
живёт в пакете ``dp_typing``.
"""

from __future__ import annotations

import sys

TK_MISSING = """\
DP Typing Master: не найден модуль tkinter.

Он входит в стандартную библиотеку Python, но в Linux часто ставится
отдельным пакетом:

    Debian/Ubuntu   sudo apt install python3-tk
    Fedora          sudo dnf install python3-tkinter
    Arch            sudo pacman -S tk

На Windows и macOS переустановите Python с python.org — там tkinter
включён в дистрибутив.
"""


def main() -> int:
    try:
        import tkinter  # noqa: F401
    except ModuleNotFoundError:
        print(TK_MISSING, file=sys.stderr)
        return 1

    from dp_typing.app import main as run_app

    return run_app()


if __name__ == "__main__":
    raise SystemExit(main())
