"""Optional PC floating timer window."""

from __future__ import annotations

import customtkinter as ctk

from ui_theme import COLORS


class FloatingTimerWindow(ctk.CTkToplevel):
    """Optional duplicate timer on PC."""

    def __init__(self, master, on_close=None) -> None:
        super().__init__(master)
        self.title("Таймер клуба (ПК)")
        self.geometry("420x220")
        self.configure(fg_color="#0a0a12")
        self.attributes("-topmost", True)
        self.resizable(True, True)
        self.minsize(280, 160)

        self._on_close_cb = on_close
        self._fullscreen = False
        self._normal_geom = "420x220"

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=12, pady=(10, 0))
        ctk.CTkLabel(header, text="КЛУБ · ТАЙМЕР (ПК)", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLORS["text_muted"]).pack(
            side="left"
        )
        ctk.CTkButton(header, text="⛶", width=32, height=28, fg_color=COLORS["btn_muted"], command=self._toggle_fullscreen).pack(
            side="right", padx=2
        )
        ctk.CTkButton(header, text="—", width=32, height=28, fg_color=COLORS["btn_muted"], command=self.withdraw).pack(side="right")

        self.label_text = ctk.CTkLabel(self, text="Сессия", font=ctk.CTkFont(size=14), text_color=COLORS["text_muted"])
        self.label_text.pack(pady=(8, 0))

        self.time_label = ctk.CTkLabel(
            self,
            text="00:00",
            font=ctk.CTkFont(family="Consolas", size=72, weight="bold"),
            text_color=COLORS["online"],
        )
        self.time_label.pack(expand=True)

        self.hint = ctk.CTkLabel(
            self,
            text="Дубликат для администратора · основной таймер на TV",
            font=ctk.CTkFont(size=10),
            text_color=COLORS["text_muted"],
        )
        self.hint.pack(pady=(0, 10))

        self.protocol("WM_DELETE_WINDOW", self._hide)

    def _hide(self) -> None:
        self.withdraw()
        if self._on_close_cb:
            self._on_close_cb()

    def _toggle_fullscreen(self) -> None:
        if not self._fullscreen:
            self._normal_geom = self.geometry()
            self.attributes("-fullscreen", True)
            self._fullscreen = True
            self.time_label.configure(font=ctk.CTkFont(family="Consolas", size=120, weight="bold"))
        else:
            self.attributes("-fullscreen", False)
            self.geometry(self._normal_geom)
            self._fullscreen = False
            self.time_label.configure(font=ctk.CTkFont(family="Consolas", size=72, weight="bold"))

    def update_timer(self, display: str, label: str, urgent: bool = False) -> None:
        if not self.winfo_viewable():
            self.deiconify()
        self.time_label.configure(text=display, text_color=COLORS["btn_power"] if urgent else COLORS["online"])
        self.label_text.configure(text=label or "Сессия")

    def show_idle(self) -> None:
        self.time_label.configure(text="—:—", text_color=COLORS["text_muted"])
        self.label_text.configure(text="Таймер не запущен")
