"""Nonblocking optional key feedback; no third-party sound dependencies."""

from __future__ import annotations

import sys
import tkinter as tk


def play(widget: tk.Misc, correct: bool) -> None:
    if sys.platform == "win32":
        try:
            import winsound

            name = "SystemAsterisk" if correct else "SystemHand"
            winsound.PlaySound(name, winsound.SND_ALIAS | winsound.SND_ASYNC |
                               winsound.SND_NODEFAULT)
            return
        except (ImportError, OSError, RuntimeError):
            pass
    try:
        widget.bell()
    except tk.TclError:
        pass
