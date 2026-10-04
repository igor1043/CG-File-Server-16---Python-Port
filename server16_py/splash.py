from __future__ import annotations

import ctypes
import time
import tkinter as tk
from tkinter import ttk

from . import __version__


def enable_dpi_awareness() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass


class SplashScreen:
    """Small splash window created and destroyed on the Tk owner thread.

    Tk/Tcl interpreters are thread-affine.  The previous implementation built
    this window in a worker thread and then created the main application Tk in
    the main thread, which could terminate the frozen executable inside
    ``tcl86t.dll`` during startup or shutdown.
    """

    def __init__(self, message: str = "", master=None) -> None:
        self._message = message
        self._master = master
        self._shown_at = 0.0
        self._root = None
        self._message_label = None
        self._progress = None
        self._create()

    def set_message(self, message: str) -> None:
        self._message = message
        if self._message_label is None or self._root is None:
            return
        try:
            self._message_label.configure(text=message)
            self._root.update_idletasks()
            self._root.update()
        except Exception:
            pass

    def close(self, *, wait: bool = True, min_visible: float = 0.0) -> None:
        if self._shown_at and min_visible > 0:
            remaining = min_visible - (time.perf_counter() - self._shown_at)
            if remaining > 0:
                time.sleep(remaining)
        root, self._root = self._root, None
        self._message_label = None
        self._progress = None
        if root is not None:
            try:
                root.destroy()
            except Exception:
                pass

    def _create(self) -> None:
        root = None
        try:
            root = tk.Toplevel(self._master) if self._master is not None else tk.Tk()
            if getattr(tk, "_default_root", None) is root:
                tk._default_root = None
            root.withdraw()
            root.overrideredirect(True)
            root.configure(bg="#111a2b")
            root.resizable(False, False)
            try:
                root.attributes("-topmost", True)
            except Exception:
                pass

            frame = tk.Frame(root, bg="#111a2b", highlightthickness=1, highlightbackground="#22314b", padx=24, pady=20)
            frame.pack(fill="both", expand=True)
            tk.Label(
                frame,
                text="CG SERVER 16",
                bg="#111a2b",
                fg="#e6edf3",
                font=("Bahnschrift", 20, "bold"),
            ).pack(anchor="w")
            tk.Label(
                frame,
                text=f"Python Port  v{__version__}",
                bg="#111a2b",
                fg="#93a1b2",
                font=("Bahnschrift", 10),
            ).pack(anchor="w", pady=(2, 12))
            message_label = tk.Label(
                frame,
                text=self._message,
                bg="#111a2b",
                fg="#4cc2ff",
                font=("Bahnschrift", 10),
                anchor="w",
            )
            message_label.pack(fill="x")
            progress = ttk.Progressbar(frame, mode="indeterminate", length=360)
            progress.pack(fill="x", pady=(12, 0))
            root.update_idletasks()
            width = max(440, root.winfo_reqwidth())
            height = max(160, root.winfo_reqheight())
            x = max(0, (root.winfo_screenwidth() - width) // 2)
            y = max(0, (root.winfo_screenheight() - height) // 2)
            root.geometry(f"{width}x{height}+{x}+{y}")
            root.deiconify()
            root.update()
            self._shown_at = time.perf_counter()
            self._root = root
            self._message_label = message_label
            self._progress = progress
        except Exception:
            if root is not None:
                try:
                    root.destroy()
                except Exception:
                    pass
