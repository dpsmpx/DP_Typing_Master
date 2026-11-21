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

    # CI runs this mode against the actual PyInstaller GUI executable.
    # It creates the real Tk window and verifies bundled language resources,
    # then closes without entering the event loop or editing the user profile.
    if sys.argv[1:] == ["--smoke-test"]:
        from dp_typing.app import TypingApp
        from dp_typing.words import load_words

        for lang in ("ru", "en"):
            if not load_words(lang):
                raise RuntimeError(f"Empty bundled dictionary: {lang}")
        app = TypingApp()
        try:
            app.update_idletasks()
            app.update()
            if app.session is None or not app.session.target:
                raise RuntimeError("Typing session failed to initialize")
            # The packaged application must also accept a genuine Tk key
            # event (not only start up and display its initial phrase).
            app._start_session("aba")
            app.event_generate("<KeyPress>", keysym="a")
            app.update()
            if app.session.pos != 1 or app.session.errors:
                raise RuntimeError("Bundled application did not handle KeyPress")
        finally:
            app.destroy()
        return 0

    from dp_typing.app import main as run_app

    return run_app()


if __name__ == "__main__":
    raise SystemExit(main())
