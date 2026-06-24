"""Control Center — CRM-панель: TV (EvoTV) + управление ПК."""

from __future__ import annotations

import io
import subprocess
import threading
import tkinter as tk
import winsound
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog

import customtkinter as ctk
from PIL import Image, ImageTk

from adb_client import EvoAdbClient, KEYCODES
from club_timer import ClubTimer, TimerState, format_duration_for_input, parse_time_input
from config import load_config, save_config
from pc_control import PCController, format_uptime
from timer_overlay import FloatingTimerWindow
from tv_registry import get_tv, make_tv, save_tv_connection
from tv_timer_display import dismiss_tv_timer, show_timer_on_tv
from tv_overlay import hide_overlay_timer, show_overlay_on_tv
from ui_theme import COLORS, QUICK_APP_STYLES
from wol import wake as wol_wake

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

QUICK_APPS = [
    ("YouTube", "com.google.android.youtube", "com.google.android.youtube.app.honeycomb.Shell$HomeActivity"),
    ("Настройки", "com.android.settings", "com.android.settings.Settings"),
    ("Браузер", "com.android.browser", ""),
    ("Netflix", "com.netflix.mediaclient", ""),
]

SIDEBAR_ITEMS = [
    ("dashboard", "Обзор"),
    ("club", "Клуб · Таймер"),
    ("tv", "Пульт TV"),
    ("tv_system", "Система TV"),
    ("pc", "Компьютер"),
    ("devices", "Устройства"),
]

SHELL_PRESETS = [
    ("getprop", "getprop"),
    ("Процессы", "ps"),
    ("Память", "cat /proc/meminfo | head -5"),
    ("Диск", "df -h"),
    ("Logcat", "logcat -d -t 30"),
    ("Wi-Fi IP", "getprop dhcp.wlan0.ipaddress"),
    ("Root?", "id"),
]


class ControlCenterApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Control Center")
        self.geometry("980x760")
        self.minsize(900, 700)
        self.configure(fg_color=COLORS["app_bg"])

        self.pc = PCController()
        self.config_data = load_config()
        self._active_tv_id: str = self.config_data.get("active_tv_id", "")
        self._tv_clients: dict[str, EvoAdbClient] = {}
        self._tv_timers: dict[str, ClubTimer] = {}
        self._tv_info: dict[str, str] = {}
        self._tv_card_status: dict[str, ctk.CTkLabel] = {}
        for tv in self.config_data.get("tvs", []):
            self._get_tv_timer(tv["id"])

        self._busy = False
        self._drag_start: tuple[int, int] | None = None
        self._nav_buttons: dict[str, ctk.CTkButton] = {}
        self._pages: dict[str, ctk.CTkFrame] = {}
        self._stat_labels: dict[str, ctk.CTkLabel] = {}
        self._stats_timer: str | None = None
        self._mirror_running = False
        self._mirror_timer: str | None = None
        self._screen_size = (1920, 1080)
        self._mirror_photo = None
        self._shell_history: list[str] = []
        self._shell_hist_idx = -1
        self._current_fs_path = "/sdcard"
        self._tv_key_bind_ids: list[str] = []

        self._club_ui_timer: str | None = None
        self._floating_timer: FloatingTimerWindow | None = None
        self._tv_timer_browser_open: dict[str, bool] = {}
        self._tv_overlay_active: dict[str, bool] = {}

        self._build_shell()
        self._show_page("dashboard")
        self._refresh_stats()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── Layout ──────────────────────────────────────────────────────────

    def _build_shell(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        sidebar = ctk.CTkFrame(self, width=210, corner_radius=0, fg_color=COLORS["sidebar"])
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)

        brand = ctk.CTkFrame(sidebar, fg_color="transparent")
        brand.pack(fill="x", padx=18, pady=(28, 24))
        ctk.CTkLabel(
            brand,
            text="Control Center",
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
            text_color=COLORS["text"],
        ).pack(anchor="w")
        ctk.CTkLabel(
            brand,
            text="Умный пульт и панель",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=COLORS["text_muted"],
        ).pack(anchor="w", pady=(2, 0))
        self.sidebar_active_tv = ctk.CTkLabel(
            brand,
            text="",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=COLORS["accent"],
        )
        self.sidebar_active_tv.pack(anchor="w", pady=(6, 0))

        ctk.CTkFrame(sidebar, height=1, fg_color=COLORS["card_border"]).pack(fill="x", padx=16, pady=(0, 12))

        for key, label in SIDEBAR_ITEMS:
            btn = ctk.CTkButton(
                sidebar,
                text=f"  {label}",
                anchor="w",
                height=44,
                corner_radius=10,
                font=ctk.CTkFont(family="Segoe UI", size=13),
                fg_color="transparent",
                text_color=COLORS["text"],
                hover_color=COLORS["sidebar_hover"],
                command=lambda k=key: self._show_page(k),
            )
            btn.pack(fill="x", padx=14, pady=3)
            self._nav_buttons[key] = btn

        self.sidebar_timer = ctk.CTkLabel(
            sidebar,
            text="",
            font=ctk.CTkFont(family="Consolas", size=13, weight="bold"),
            text_color=COLORS["online"],
        )
        self.sidebar_timer.pack(padx=18, pady=(8, 16), anchor="w")

        self.content = ctk.CTkFrame(self, fg_color="transparent")
        self.content.grid(row=0, column=1, sticky="nsew", padx=(0, 12), pady=12)
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

        self._build_dashboard()
        self._build_club_page()
        self._build_tv_page()
        self._build_tv_system_page()
        self._build_pc_page()
        self._build_devices_page()

        log_frame = ctk.CTkFrame(self.content, height=90)
        log_frame.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        log_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(log_frame, text="Журнал", anchor="w", font=ctk.CTkFont(size=11, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=10, pady=(6, 0)
        )
        self.log_box = ctk.CTkTextbox(log_frame, height=60, font=ctk.CTkFont(family="Consolas", size=11))
        self.log_box.grid(row=1, column=0, sticky="ew", padx=10, pady=(2, 8))
        self.log_box.configure(state="disabled")

    def _page(self, key: str) -> ctk.CTkScrollableFrame:
        frame = ctk.CTkScrollableFrame(self.content, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)
        self._pages[key] = frame
        return frame

    def _show_page(self, key: str) -> None:
        self._unbind_tv_keys()
        if key != "tv_system":
            self._stop_mirror()
        for k, frame in self._pages.items():
            frame.grid_forget()
        self._pages[key].grid(row=0, column=0, sticky="nsew")
        for k, btn in self._nav_buttons.items():
            if k == key:
                btn.configure(fg_color=COLORS["sidebar_active"], hover_color=COLORS["sidebar_active"])
            else:
                btn.configure(fg_color="transparent", hover_color=COLORS["sidebar_hover"])
        if key == "tv":
            self._bind_tv_keys()
        if key in ("dashboard", "pc"):
            self._refresh_stats()
        if key == "dashboard":
            self._render_tv_list()
        if key == "club":
            self._sync_active_tv_ui()
        if key == "tv":
            self._sync_active_tv_ui()
        if key == "tv_system" and self.tv_client.connected:
            self._refresh_fs_list()
            self._refresh_apps_list()

    def _card(self, parent, title: str, row: int, col: int = 0, colspan: int = 1) -> ctk.CTkFrame:
        card = ctk.CTkFrame(parent, fg_color=COLORS["card"], corner_radius=14, border_width=1, border_color=COLORS["card_border"])
        card.grid(row=row, column=col, columnspan=colspan, sticky="nsew", padx=6, pady=6)
        ctk.CTkLabel(card, text=title, font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"), anchor="w", text_color=COLORS["text"]).pack(
            anchor="w", padx=16, pady=(14, 6)
        )
        body = ctk.CTkFrame(card, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=16, pady=(0, 14))
        return body

    # ── Dashboard ─────────────────────────────────────────────────────

    def _build_dashboard(self) -> None:
        page = self._page("dashboard")
        ctk.CTkLabel(
            page,
            text="Обзор системы",
            font=ctk.CTkFont(size=24, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=6, pady=(0, 8))

        cards = ctk.CTkFrame(page, fg_color="transparent")
        cards.grid(row=1, column=0, sticky="ew")
        cards.grid_columnconfigure((0, 1), weight=1)

        pc_body = self._card(cards, "💻  Этот компьютер", 0, 0)
        self._stat_labels["dash_pc"] = ctk.CTkLabel(
            pc_body, text="Загрузка...", justify="left", anchor="w", font=ctk.CTkFont(size=12)
        )
        self._stat_labels["dash_pc"].pack(anchor="w")
        pc_actions = ctk.CTkFrame(pc_body, fg_color="transparent")
        pc_actions.pack(anchor="w", pady=(10, 0))
        for text, cmd, color in [
            ("🔒 Блок", self._pc_lock, "#444"),
            ("💤 Сон", self._pc_sleep, "#555"),
            ("⏻ Выкл", self._pc_shutdown, "#8b0000"),
        ]:
            ctk.CTkButton(pc_actions, text=text, width=80, fg_color=color, command=cmd).pack(side="left", padx=3)

        tv_body = self._card(cards, "📺  Активный TV", 0, 1)
        self._stat_labels["dash_tv"] = ctk.CTkLabel(
            tv_body, text="Загрузка...", justify="left", anchor="w", font=ctk.CTkFont(size=12)
        )
        self._stat_labels["dash_tv"].pack(anchor="w")

        tv_list_card = self._card(page, "📺  Телевизоры клуба — нажмите для пульта и таймера", 2, colspan=1)
        self._tv_list_frame = ctk.CTkFrame(tv_list_card, fg_color="transparent")
        self._tv_list_frame.pack(fill="x")
        add_tv_row = ctk.CTkFrame(tv_list_card, fg_color="transparent")
        add_tv_row.pack(anchor="w", pady=(10, 0))
        ctk.CTkButton(add_tv_row, text="+ Добавить TV", width=140, command=self._add_tv).pack(side="left", padx=(0, 8))
        ctk.CTkButton(add_tv_row, text="✎ Изменить", width=100, fg_color=COLORS["btn_nav"], command=self._edit_active_tv).pack(
            side="left", padx=4
        )

        quick = self._card(page, "⚡  Быстрые действия", 3, colspan=1)
        row = ctk.CTkFrame(quick, fg_color="transparent")
        row.pack(anchor="w")
        actions = [
            ("Перезагрузить ПК", self._pc_restart),
            ("Гибернация ПК", self._pc_hibernate),
            ("Отменить выключение", self._pc_cancel_shutdown),
            ("Подключить TV", lambda: (self._show_page("tv"), self._toggle_tv_connection())),
            ("Разбудить ПК (WoL)", lambda: self._show_page("devices")),
        ]
        for i, (text, cmd) in enumerate(actions):
            ctk.CTkButton(row, text=text, width=160, command=cmd).grid(row=i // 3, column=i % 3, padx=4, pady=4)

        self._render_tv_list()
        self._sync_active_tv_ui()

    # ── TV registry ─────────────────────────────────────────────────────

    @property
    def tv_client(self) -> EvoAdbClient:
        return self._get_tv_client(self._active_tv_id)

    @property
    def club_timer(self) -> ClubTimer:
        return self._get_tv_timer(self._active_tv_id)

    def _get_tv_timer(self, tv_id: str) -> ClubTimer:
        if tv_id not in self._tv_timers:
            timer = ClubTimer()
            timer.set_callbacks(
                on_tick=lambda snap, tid=tv_id: self._on_club_tick(tid, snap),
                on_finish=lambda tid=tv_id: self._on_club_finish(tid),
            )
            self._tv_timers[tv_id] = timer
        return self._tv_timers[tv_id]

    def _get_tv_client(self, tv_id: str) -> EvoAdbClient:
        if tv_id not in self._tv_clients:
            self._tv_clients[tv_id] = EvoAdbClient()
        return self._tv_clients[tv_id]

    def _active_tv_record(self) -> dict:
        return get_tv(self.config_data, self._active_tv_id) or {}

    def _select_tv(self, tv_id: str, *, save: bool = True) -> None:
        if not any(t["id"] == tv_id for t in self.config_data.get("tvs", [])):
            return
        self._active_tv_id = tv_id
        self.config_data["active_tv_id"] = tv_id
        tv = get_tv(self.config_data, tv_id)
        if tv:
            self.config_data["host"] = tv["host"]
            self.config_data["port"] = tv["port"]
            if save:
                save_config(self.config_data)
        self._sync_active_tv_ui()
        self._render_tv_list()

    def _sync_active_tv_ui(self) -> None:
        tv = self._active_tv_record()
        if hasattr(self, "host_entry"):
            self.host_entry.delete(0, "end")
            self.host_entry.insert(0, tv.get("host", self.config_data.get("host", "")))
        if hasattr(self, "port_entry"):
            self.port_entry.delete(0, "end")
            self.port_entry.insert(0, str(tv.get("port", self.config_data.get("port", 5555))))
        client = self._get_tv_client(self._active_tv_id)
        if hasattr(self, "connect_btn"):
            if client.connected:
                self.connect_btn.configure(text="Отключиться", fg_color=COLORS["btn_muted"], state="normal")
                self._set_tv_status(f"Подключено · {client.address}", "online")
            else:
                self.connect_btn.configure(text="Подключиться", fg_color=COLORS["accent"], state="normal")
                self._set_tv_status("Не подключено", "offline")
        if hasattr(self, "club_active_tv_label"):
            name = tv.get("name", "TV")
            self.club_active_tv_label.configure(text=f"📺 {name}")
        if hasattr(self, "club_label_entry"):
            self.club_label_entry.delete(0, "end")
            self.club_label_entry.insert(0, tv.get("club_label", self.config_data.get("club_label", "ПК-1")))
        if hasattr(self, "club_big_time"):
            self._update_club_ui(self.club_timer.snapshot())
        name = tv.get("name", "")
        if hasattr(self, "sidebar_active_tv"):
            self.sidebar_active_tv.configure(text=f"TV: {name}" if name else "")
        if hasattr(self, "tv_page_subtitle"):
            self.tv_page_subtitle.configure(
                text=f"Управление: {name}  ·  {tv.get('host', '')}:{tv.get('port', 5555)}"
            )

    def _open_tv(self, tv_id: str) -> None:
        self._select_tv(tv_id)
        client = self._get_tv_client(tv_id)
        if client.connected:
            self._show_page("club")
            return
        self._connect_tv_id(tv_id, then_page="club")

    def _connect_tv_id(
        self, tv_id: str, *, then_page: str | None = None, on_success=None
    ) -> None:
        tv = get_tv(self.config_data, tv_id)
        if not tv:
            return
        self._select_tv(tv_id, save=False)
        host = tv["host"]
        port = int(tv["port"])
        save_tv_connection(self.config_data, tv_id, host, port)
        save_config(self.config_data)

        if hasattr(self, "connect_btn"):
            self.connect_btn.configure(state="disabled", text="Подключение...")
        self._set_tv_status("Подключение...", "connecting")
        self._log(f"TV {tv.get('name', '')}: подключение к {host}:{port}...")

        client = self._get_tv_client(tv_id)

        def done(result):
            if hasattr(self, "connect_btn"):
                self.connect_btn.configure(state="normal")
            if result.ok:
                if hasattr(self, "connect_btn"):
                    self.connect_btn.configure(text="Отключиться", fg_color=COLORS["btn_muted"])
                short = result.output.replace("Подключено: ", "")
                self._set_tv_status(f"Подключено · {short}", "online")
                self._tv_info[tv_id] = result.output
                self._log(f"TV {tv.get('name', '')}: {result.output}")
            else:
                if hasattr(self, "connect_btn"):
                    self.connect_btn.configure(text="Подключиться", fg_color=COLORS["accent"])
                self._set_tv_status("Ошибка подключения", "offline")
                self._log(f"TV {tv.get('name', '')}: {result.error}")
                messagebox.showwarning("TV", result.error)
            self._render_tv_list()
            if then_page:
                self._show_page(then_page)
            if result.ok and on_success:
                on_success()

        self._run_async(lambda: client.connect(host, port), done)

    def _open_tv_remote(self, tv_id: str) -> None:
        self._select_tv(tv_id)
        self._show_page("tv")
        if not self._get_tv_client(tv_id).connected:
            self._connect_tv_id(tv_id)

    def _render_tv_list(self) -> None:
        if not hasattr(self, "_tv_list_frame"):
            return
        for w in self._tv_list_frame.winfo_children():
            w.destroy()
        self._tv_card_status.clear()
        tvs = self.config_data.get("tvs", [])
        if not tvs:
            ctk.CTkLabel(self._tv_list_frame, text="Нет TV — нажмите «+ Добавить TV»", text_color=COLORS["text_muted"]).pack(
                anchor="w"
            )
            return
        for i, tv in enumerate(tvs):
            tv_id = tv["id"]
            client = self._get_tv_client(tv_id)
            timer = self._get_tv_timer(tv_id)
            snap = timer.snapshot()
            is_active = tv_id == self._active_tv_id
            row = ctk.CTkFrame(
                self._tv_list_frame,
                fg_color=COLORS["sidebar_active"] if is_active else COLORS["remote_body"],
                corner_radius=10,
                border_width=1 if is_active else 0,
                border_color=COLORS["accent"],
            )
            row.pack(fill="x", pady=4)
            row.bind("<Button-1>", lambda e, tid=tv_id: self._open_tv(tid))

            dot_color = COLORS["online"] if client.connected else COLORS["offline"]
            dot = ctk.CTkFrame(row, width=10, height=10, corner_radius=5, fg_color=dot_color)
            dot.pack(side="left", padx=(12, 8), pady=12)

            info = ctk.CTkFrame(row, fg_color="transparent")
            info.pack(side="left", fill="x", expand=True, pady=8)
            title = ctk.CTkLabel(
                info,
                text=tv.get("name", f"TV-{i + 1}"),
                font=ctk.CTkFont(size=14, weight="bold"),
                anchor="w",
            )
            title.pack(anchor="w")
            title.bind("<Button-1>", lambda e, tid=tv_id: self._open_tv(tid))
            sub = f"{tv.get('host', '')}:{tv.get('port', 5555)}"
            if tv.get("club_label"):
                sub += f"  ·  {tv['club_label']}"
            ctk.CTkLabel(info, text=sub, font=ctk.CTkFont(size=11), text_color=COLORS["text_muted"], anchor="w").pack(
                anchor="w"
            )

            timer_text = ""
            if snap.state == TimerState.RUNNING:
                timer_text = f"⏱ {snap.display}"
            elif snap.state == TimerState.PAUSED:
                timer_text = f"⏸ {snap.display}"
            status_lbl = ctk.CTkLabel(
                row, text=timer_text, font=ctk.CTkFont(family="Consolas", size=13, weight="bold"), text_color=COLORS["online"]
            )
            status_lbl.pack(side="left", padx=8)
            self._tv_card_status[tv_id] = status_lbl

            actions = ctk.CTkFrame(row, fg_color="transparent")
            actions.pack(side="right", padx=8, pady=8)
            ctk.CTkButton(
                actions, text="Таймер", width=72, height=32, fg_color=COLORS["btn_success"], command=lambda tid=tv_id: self._open_tv(tid)
            ).pack(side="left", padx=2)
            ctk.CTkButton(
                actions,
                text="Пульт",
                width=72,
                height=32,
                command=lambda tid=tv_id: self._open_tv_remote(tid),
            ).pack(side="left", padx=2)
            if len(tvs) > 1:
                ctk.CTkButton(
                    actions, text="✕", width=32, height=32, fg_color=COLORS["btn_muted"], command=lambda tid=tv_id: self._remove_tv(tid)
                ).pack(side="left", padx=2)

    def _add_tv(self) -> None:
        n = len(self.config_data.get("tvs", [])) + 1
        name = simpledialog.askstring("Новый TV", f"Название (например TV-{n}):", parent=self, initialvalue=f"TV-{n}")
        if not name:
            return
        host = simpledialog.askstring("IP-адрес", "IP телевизора:", parent=self, initialvalue="192.168.2.")
        if not host:
            return
        port_s = simpledialog.askstring("Порт ADB", "Порт (обычно 5555):", parent=self, initialvalue="5555")
        if not port_s:
            return
        try:
            port = int(port_s.strip())
        except ValueError:
            messagebox.showerror("TV", "Неверный порт")
            return
        label = simpledialog.askstring("Место", "Название места / ПК (необязательно):", parent=self) or ""
        tv = make_tv(name=name, host=host, port=port, club_label=label)
        self.config_data.setdefault("tvs", []).append(tv)
        self._get_tv_timer(tv["id"])
        save_config(self.config_data)
        self._select_tv(tv["id"])
        self._render_tv_list()
        self._log(f"Добавлен {name} — {host}:{port}")

    def _edit_active_tv(self) -> None:
        tv = self._active_tv_record()
        if not tv:
            return
        self._edit_tv(tv["id"])

    def _edit_tv(self, tv_id: str) -> None:
        tv = get_tv(self.config_data, tv_id)
        if not tv:
            return
        name = simpledialog.askstring("TV", "Название:", parent=self, initialvalue=tv.get("name", ""))
        if not name:
            return
        host = simpledialog.askstring("TV", "IP:", parent=self, initialvalue=tv.get("host", ""))
        if not host:
            return
        port_s = simpledialog.askstring("TV", "Порт ADB:", parent=self, initialvalue=str(tv.get("port", 5555)))
        if not port_s:
            return
        try:
            port = int(port_s.strip())
        except ValueError:
            messagebox.showerror("TV", "Неверный порт")
            return
        label = simpledialog.askstring("TV", "Место / ПК:", parent=self, initialvalue=tv.get("club_label", ""))
        tv["name"] = name.strip()
        tv["host"] = host.strip()
        tv["port"] = port
        tv["club_label"] = (label or "").strip()
        if tv_id == self._active_tv_id:
            self.config_data["host"] = tv["host"]
            self.config_data["port"] = tv["port"]
        save_config(self.config_data)
        self._sync_active_tv_ui()
        self._render_tv_list()
        self._log(f"Обновлён {name}")

    def _remove_tv(self, tv_id: str) -> None:
        tvs = self.config_data.get("tvs", [])
        if len(tvs) <= 1:
            messagebox.showinfo("TV", "Нужен хотя бы один телевизор в списке.")
            return
        tv = get_tv(self.config_data, tv_id)
        if not tv:
            return
        if not messagebox.askyesno("TV", f"Удалить {tv.get('name', 'TV')} из списка?"):
            return
        self._get_tv_client(tv_id).disconnect()
        self._tv_clients.pop(tv_id, None)
        self._tv_timers.pop(tv_id, None)
        self.config_data["tvs"] = [t for t in tvs if t["id"] != tv_id]
        if self._active_tv_id == tv_id:
            self._active_tv_id = self.config_data["tvs"][0]["id"]
            self.config_data["active_tv_id"] = self._active_tv_id
        save_config(self.config_data)
        self._sync_active_tv_ui()
        self._render_tv_list()
        self._log(f"Удалён {tv.get('name', 'TV')}")

    # ── Club timer ──────────────────────────────────────────────────────

    def _build_club_page(self) -> None:
        page = self._page("club")
        ctk.CTkLabel(
            page,
            text="Клуб · таймер сессии",
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color=COLORS["text"],
        ).grid(row=0, column=0, sticky="w", padx=6, pady=(0, 4))
        ctk.CTkLabel(
            page,
            text="Таймер в правом верхнем углу TV — виден даже при PS/HDMI (оверлей Android).\n"
            "Один раз: build_overlay.bat → установка APK на TV. TV подключён по ADB.",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_muted"],
            justify="left",
        ).grid(row=1, column=0, sticky="w", padx=6, pady=(0, 12))

        head = ctk.CTkFrame(page, fg_color="transparent")
        head.grid(row=2, column=0, sticky="ew", padx=6, pady=(0, 8))
        self.club_active_tv_label = ctk.CTkLabel(
            head, text="📺 TV-1", font=ctk.CTkFont(size=16, weight="bold"), text_color=COLORS["accent"]
        )
        self.club_active_tv_label.pack(side="left")
        ctk.CTkButton(
            head, text="⏱ Таймер", width=100, fg_color=COLORS["btn_success"], command=lambda: self._show_page("club")
        ).pack(side="right", padx=4)
        ctk.CTkButton(
            head, text="📺 Пульт", width=100, fg_color=COLORS["btn_nav"], command=lambda: self._show_page("tv")
        ).pack(side="right", padx=4)
        ctk.CTkButton(
            head, text="← Все TV", width=100, fg_color="transparent", border_width=1, border_color=COLORS["card_border"],
            command=lambda: self._show_page("dashboard"),
        ).pack(side="right", padx=4)

        main_card = ctk.CTkFrame(page, fg_color=COLORS["card"], corner_radius=16, border_width=1, border_color=COLORS["card_border"])
        main_card.grid(row=3, column=0, sticky="ew", padx=6, pady=4)
        main_card.grid_columnconfigure(0, weight=1)

        default_min = int(self.config_data.get("club_default_minutes", 60))
        time_wrap = ctk.CTkFrame(main_card, fg_color="transparent")
        time_wrap.pack(pady=(24, 4))
        self.club_big_time = ctk.CTkEntry(
            time_wrap,
            width=320,
            height=100,
            justify="center",
            font=ctk.CTkFont(family="Consolas", size=72, weight="bold"),
            text_color=COLORS["online"],
            corner_radius=12,
            border_width=2,
            border_color=COLORS["card_border"],
        )
        self.club_big_time.insert(0, format_duration_for_input(default_min * 60))
        self.club_big_time.pack()
        self.club_big_time.bind("<Return>", lambda e: self._club_start())
        self.club_big_time.bind("<FocusOut>", lambda e: self._club_sync_minutes_from_time())
        ctk.CTkLabel(
            time_wrap,
            text="Введите время: 60  ·  90:00  ·  1:30:00  ·  Enter = старт",
            font=ctk.CTkFont(size=11),
            text_color=COLORS["text_muted"],
        ).pack(pady=(6, 0))
        self.club_status = ctk.CTkLabel(main_card, text="Таймер не запущен", font=ctk.CTkFont(size=14), text_color=COLORS["text_muted"])
        self.club_status.pack(pady=(0, 16))

        form = ctk.CTkFrame(main_card, fg_color="transparent")
        form.pack(fill="x", padx=20, pady=(0, 12))
        ctk.CTkLabel(form, text="Название места / ПК:").grid(row=0, column=0, sticky="w", pady=4)
        self.club_label_entry = ctk.CTkEntry(form, width=280, placeholder_text="ПК-1 / PS-2")
        active = self._active_tv_record()
        self.club_label_entry.insert(0, active.get("club_label") or self.config_data.get("club_label", "ПК-1"))
        self.club_label_entry.grid(row=0, column=1, padx=8, pady=4, sticky="w")

        ctk.CTkLabel(form, text="Или минут:").grid(row=1, column=0, sticky="w", pady=4)
        self.club_minutes_entry = ctk.CTkEntry(form, width=80)
        self.club_minutes_entry.insert(0, str(default_min))
        self.club_minutes_entry.grid(row=1, column=1, padx=8, pady=4, sticky="w")
        self.club_minutes_entry.bind("<Return>", lambda e: self._club_start())
        self.club_minutes_entry.bind("<FocusOut>", lambda e: self._club_sync_time_from_minutes())

        presets = ctk.CTkFrame(main_card, fg_color="transparent")
        presets.pack(pady=4)
        for mins, label in [(30, "30 мин"), (60, "1 час"), (90, "1.5 ч"), (120, "2 часа")]:
            ctk.CTkButton(
                presets,
                text=label,
                width=90,
                fg_color=COLORS["btn_nav"],
                command=lambda m=mins: self._club_start_preset(m),
            ).pack(side="left", padx=4)

        ctrl = ctk.CTkFrame(main_card, fg_color="transparent")
        ctrl.pack(pady=(8, 20))
        ctk.CTkButton(ctrl, text="▶ Старт", width=100, fg_color=COLORS["btn_success"], command=self._club_start).pack(
            side="left", padx=4
        )
        ctk.CTkButton(ctrl, text="⏸ Пауза", width=100, fg_color=COLORS["btn_muted"], command=self._club_pause_resume).pack(
            side="left", padx=4
        )
        ctk.CTkButton(ctrl, text="+15 мин", width=90, command=lambda: self._club_add(15)).pack(side="left", padx=4)
        ctk.CTkButton(ctrl, text="⏹ Стоп", width=90, fg_color=COLORS["btn_power"], command=self._club_stop).pack(
            side="left", padx=4
        )
        ctk.CTkButton(ctrl, text="📺 На TV", width=120, command=self._club_show_on_tv).pack(side="left", padx=4)
        ctk.CTkButton(ctrl, text="⬇ Оверлей", width=100, command=self._club_install_overlay).pack(side="left", padx=4)

        opts = self._card(page, "⚙  Настройки клуба", 4)
        self.club_auto_off = ctk.CTkCheckBox(
            opts,
            text="Выключить TV автоматически по окончании",
            font=ctk.CTkFont(size=12),
        )
        self.club_auto_off.pack(anchor="w", pady=4)
        if self.config_data.get("club_auto_tv_off", True):
            self.club_auto_off.select()

        self.club_tv_overlay_cb = ctk.CTkCheckBox(
            opts,
            text="Таймер в углу на TV (поверх HDMI / PS)",
            font=ctk.CTkFont(size=12),
        )
        self.club_tv_overlay_cb.pack(anchor="w", pady=4)
        if self.config_data.get("club_tv_corner_overlay", True):
            self.club_tv_overlay_cb.select()

        self.club_tv_display_cb = ctk.CTkCheckBox(
            opts,
            text="Дополнительно: полный экран в браузере TV",
            font=ctk.CTkFont(size=12),
        )
        self.club_tv_display_cb.pack(anchor="w", pady=4)
        if self.config_data.get("club_show_on_tv", False):
            self.club_tv_display_cb.select()

        self.club_floating_cb = ctk.CTkCheckBox(
            opts,
            text="Дублировать таймер окном на ПК (для администратора)",
            font=ctk.CTkFont(size=12),
        )
        self.club_floating_cb.pack(anchor="w", pady=4)
        if self.config_data.get("club_show_floating", False):
            self.club_floating_cb.select()

        ctk.CTkLabel(
            opts,
            text="Первый запуск: нажмите «⬇ Оверлей» или запустите build_overlay.bat.\n"
            "На TV может появиться запрос «Поверх других приложений» — разрешите.",
            font=ctk.CTkFont(size=11),
            text_color=COLORS["text_muted"],
            justify="left",
        ).pack(anchor="w", pady=(8, 0))

    def _save_club_config(self) -> None:
        label = self.club_label_entry.get().strip() if hasattr(self, "club_label_entry") else "ПК-1"
        self.config_data["club_label"] = label
        tv = get_tv(self.config_data, self._active_tv_id)
        if tv:
            tv["club_label"] = label
        try:
            self.config_data["club_default_minutes"] = int(self.club_minutes_entry.get().strip())
        except (ValueError, AttributeError):
            pass
        if hasattr(self, "club_big_time") and self.club_timer.snapshot().state == TimerState.IDLE:
            sec = parse_time_input(self.club_big_time.get().strip())
            if sec is not None:
                self.config_data["club_default_minutes"] = max(1, (sec + 59) // 60)
        if hasattr(self, "club_auto_off"):
            self.config_data["club_auto_tv_off"] = bool(self.club_auto_off.get())
            self.config_data["club_tv_corner_overlay"] = bool(self.club_tv_overlay_cb.get())
            self.config_data["club_show_on_tv"] = bool(self.club_tv_display_cb.get())
            self.config_data["club_show_floating"] = bool(self.club_floating_cb.get())
        save_config(self.config_data)

    def _club_tv_enabled(self) -> bool:
        overlay = hasattr(self, "club_tv_overlay_cb") and self.club_tv_overlay_cb.get()
        browser = hasattr(self, "club_tv_display_cb") and self.club_tv_display_cb.get()
        return bool(overlay or browser)

    def _sync_tv_displays(self, snap, *, start: bool) -> None:
        if not self.tv_client.connected or not self._club_tv_enabled():
            return
        self._run_async(
            lambda: self._sync_tv_displays_work(snap, start),
            lambda result: self._on_tv_sync(result, start),
        )

    def _sync_tv_displays_work(self, snap, start: bool, client: EvoAdbClient | None = None) -> list[tuple[str, bool, str]]:
        adb = client or self.tv_client
        results: list[tuple[str, bool, str]] = []
        if hasattr(self, "club_tv_overlay_cb") and self.club_tv_overlay_cb.get():
            ok, msg = show_overlay_on_tv(adb, snap, start_service=start)
            results.append(("overlay", ok, msg))
        if hasattr(self, "club_tv_display_cb") and self.club_tv_display_cb.get() and start:
            ok, msg = show_timer_on_tv(adb, snap, open_browser=True)
            results.append(("browser", ok, msg))
        return results

    def _on_tv_sync(self, results: list[tuple[str, bool, str]], started: bool, tv_id: str | None = None) -> None:
        if not results:
            return
        tid = tv_id or self._active_tv_id
        for kind, ok, detail in results:
            if ok:
                if kind == "overlay":
                    self._tv_overlay_active[tid] = True
                if kind == "browser" and started:
                    self._tv_timer_browser_open[tid] = True
                self._log(f"Клуб: {kind} TV — {detail[:100]}")
            else:
                self._log(f"Клуб: ошибка {kind} — {detail}")
                if started:
                    messagebox.showwarning(
                        "TV",
                        f"Не удалось показать таймер ({kind}).\n\n{detail}\n\n"
                        "Для углового таймера запустите build_overlay.bat и «⬇ Оверлей».",
                    )

    def _club_install_overlay(self) -> None:
        if not self.tv_client.connected:
            messagebox.showwarning("TV", "Сначала подключите TV на вкладке «Пульт TV».")
            return
        from tv_overlay import APK_PATH, ensure_overlay_ready, install_overlay_apk, is_overlay_installed, push_overlay_timer

        def work():
            if not is_overlay_installed(self.tv_client):
                if not APK_PATH.exists():
                    return False, f"APK не найден.\nЗапустите build_overlay.bat:\n{APK_PATH}"
                install = install_overlay_apk(self.tv_client)
                if not install.ok:
                    return False, install.error
            ready, msg = ensure_overlay_ready(self.tv_client)
            if not ready:
                return False, msg
            return True, "overlay ready"

        self._run_async(work, lambda r: self._on_overlay_installed(r))

    def _on_overlay_installed(self, result: tuple[bool, str]) -> None:
        ok, detail = result
        if ok:
            self._tv_overlay_active[self._active_tv_id] = True
            self._log("Клуб: оверлей установлен и запущен")
            messagebox.showinfo(
                "TV",
                "Оверлей установлен.\n\n"
                "Если TV спросит «Поверх других приложений» — разрешите.\n"
                "Затем запустите таймер (▶ Старт).",
            )
        else:
            messagebox.showerror(
                "TV",
                f"Не удалось установить оверлей.\n\n{detail}\n\n"
                "Запустите build_overlay.bat\n"
                "Ссылки: evo-remote\\OVERLAY_DOWNLOADS.txt",
            )

    def _club_show_on_tv(self) -> None:
        if not self.tv_client.connected:
            messagebox.showwarning(
                "TV",
                "Сначала подключите TV на вкладке «Пульт TV».\n"
                "Нужен статус device в adb devices.",
            )
            return
        snap = self.club_timer.snapshot()
        if snap.state == TimerState.IDLE:
            messagebox.showinfo("TV", "Сначала запустите таймер (▶ Старт).")
            return
        self._sync_tv_displays(snap, start=True)

    def _ensure_floating_timer(self) -> FloatingTimerWindow:
        if self._floating_timer is None or not self._floating_timer.winfo_exists():
            self._floating_timer = FloatingTimerWindow(self)
        return self._floating_timer

    def _club_show_floating(self) -> None:
        win = self._ensure_floating_timer()
        snap = self.club_timer.snapshot()
        if snap.state == TimerState.IDLE:
            win.show_idle()
        else:
            win.update_timer(snap.display, snap.label, urgent=snap.remaining_sec <= 300)
        win.deiconify()
        win.lift()

    def _club_sync_time_from_minutes(self) -> None:
        if self.club_timer.snapshot().state != TimerState.IDLE:
            return
        try:
            minutes = int(self.club_minutes_entry.get().strip())
        except ValueError:
            return
        if minutes < 1:
            return
        self._club_set_duration_display(minutes)

    def _club_sync_minutes_from_time(self) -> None:
        if self.club_timer.snapshot().state != TimerState.IDLE:
            return
        sec = parse_time_input(self.club_big_time.get().strip())
        if sec is None or not hasattr(self, "club_minutes_entry"):
            return
        self.club_minutes_entry.delete(0, "end")
        self.club_minutes_entry.insert(0, str(max(1, (sec + 59) // 60)))

    def _club_set_duration_display(self, minutes: int) -> None:
        text = format_duration_for_input(max(1, minutes) * 60)
        self.club_big_time.configure(state="normal")
        self.club_big_time.delete(0, "end")
        self.club_big_time.insert(0, text)

    def _club_read_duration_sec(self) -> int | None:
        snap = self.club_timer.snapshot()
        if snap.state != TimerState.IDLE:
            return None
        text = self.club_big_time.get().strip()
        sec = parse_time_input(text)
        if sec is not None:
            return sec
        try:
            minutes = int(self.club_minutes_entry.get().strip())
            if minutes >= 1:
                return minutes * 60
        except ValueError:
            pass
        return None

    def _club_start_preset(self, minutes: int) -> None:
        if hasattr(self, "club_minutes_entry"):
            self.club_minutes_entry.delete(0, "end")
            self.club_minutes_entry.insert(0, str(minutes))
        self._club_set_duration_display(minutes)
        self._club_start()

    def _club_start(self) -> None:
        self._save_club_config()
        total_sec = self._club_read_duration_sec()
        if total_sec is None:
            messagebox.showerror(
                "Таймер",
                "Неверное время.\n\nПримеры: 60  ·  90:00  ·  1:30:00",
            )
            return
        label = self.club_label_entry.get().strip() or "Сессия"
        self.club_timer.start_seconds(total_sec, label)
        minutes = total_sec // 60
        if hasattr(self, "club_minutes_entry"):
            self.club_minutes_entry.delete(0, "end")
            self.club_minutes_entry.insert(0, str(minutes))
        if self.club_floating_cb.get():
            self._club_show_floating()
        if self._club_tv_enabled():
            self._sync_tv_displays(self.club_timer.snapshot(), start=True)
        self._start_club_tick_loop()
        self._log(f"Клуб: старт {format_duration_for_input(total_sec)} — {label}")

    def _club_pause_resume(self) -> None:
        snap = self.club_timer.snapshot()
        if snap.state == TimerState.RUNNING:
            self.club_timer.pause()
            self._log("Клуб: пауза")
        elif snap.state == TimerState.PAUSED:
            self.club_timer.resume()
            self._start_club_tick_loop()
            self._log("Клуб: продолжение")
        if self._club_tv_enabled() and self.tv_client.connected:
            self._sync_tv_displays(self.club_timer.snapshot(), start=False)

    def _club_add(self, minutes: int) -> None:
        self.club_timer.add_minutes(minutes)
        self._log(f"Клуб: +{minutes} мин")
        if self._club_tv_enabled() and self.tv_client.connected:
            self._sync_tv_displays(self.club_timer.snapshot(), start=False)

    def _club_stop(self) -> None:
        tv_id = self._active_tv_id
        client = self._get_tv_client(tv_id)
        self.club_timer.stop()
        if not any(t.snapshot().state == TimerState.RUNNING for t in self._tv_timers.values()):
            self._stop_club_tick_loop()
        if self._tv_overlay_active.get(tv_id) and client.connected:
            self._run_async(lambda: hide_overlay_timer(client), lambda _: None)
            self._tv_overlay_active[tv_id] = False
        if self._tv_timer_browser_open.get(tv_id) and client.connected:
            self._run_async(lambda: dismiss_tv_timer(client), lambda _: None)
            self._tv_timer_browser_open[tv_id] = False
        if self._floating_timer and self._floating_timer.winfo_exists():
            self._floating_timer.show_idle()
        self._update_club_ui(self.club_timer.snapshot())
        self._log("Клуб: таймер остановлен")

    def _start_club_tick_loop(self) -> None:
        self._stop_club_tick_loop()
        self._club_ui_timer = self.after(1000, self._club_tick_loop)

    def _stop_club_tick_loop(self) -> None:
        if self._club_ui_timer:
            self.after_cancel(self._club_ui_timer)
            self._club_ui_timer = None

    def _club_tick_loop(self) -> None:
        any_running = False
        for timer in self._tv_timers.values():
            snap = timer.snapshot()
            if snap.state == TimerState.RUNNING:
                timer.tick()
                any_running = True
        if any_running:
            self._club_ui_timer = self.after(1000, self._club_tick_loop)
        else:
            self._club_ui_timer = None

    def _on_club_tick(self, tv_id: str, snap) -> None:
        self.after(0, lambda: self._on_club_tick_ui(tv_id, snap))

    def _on_club_tick_ui(self, tv_id: str, snap) -> None:
        if tv_id == self._active_tv_id:
            self._update_club_ui(snap)
        if tv_id in self._tv_card_status and self._tv_card_status[tv_id].winfo_exists():
            if snap.state == TimerState.RUNNING:
                self._tv_card_status[tv_id].configure(text=f"⏱ {snap.display}")
            elif snap.state == TimerState.PAUSED:
                self._tv_card_status[tv_id].configure(text=f"⏸ {snap.display}")
            else:
                self._tv_card_status[tv_id].configure(text="")

    def _update_club_ui(self, snap) -> None:
        urgent = snap.remaining_sec <= 300 and snap.state == TimerState.RUNNING
        color = COLORS["btn_power"] if urgent else COLORS["online"]
        default_min = int(self.config_data.get("club_default_minutes", 60))
        if snap.state == TimerState.IDLE:
            display = format_duration_for_input(default_min * 60)
            status, color = "Таймер не запущен — введите время", COLORS["online"]
            editable = True
        elif snap.state == TimerState.PAUSED:
            display, status = snap.display, f"Пауза · {snap.label}"
            color = COLORS["connecting"]
            editable = False
        elif snap.state == TimerState.FINISHED:
            display, status, color = snap.display, "Время вышло!", COLORS["btn_power"]
            editable = False
        else:
            display, status = snap.display, f"Идёт сессия · {snap.label}"
            editable = False

        if hasattr(self, "club_big_time"):
            self.club_big_time.configure(state="normal", text_color=color)
            self.club_big_time.delete(0, "end")
            self.club_big_time.insert(0, display)
            if editable:
                self.club_big_time.configure(state="normal")
            else:
                self.club_big_time.configure(state="disabled")
        if hasattr(self, "club_status"):
            self.club_status.configure(text=status)

        if snap.state in (TimerState.RUNNING, TimerState.PAUSED):
            self.sidebar_timer.configure(text=f"⏱ {display}", text_color=color)
        else:
            self.sidebar_timer.configure(text="")

        if self._floating_timer and self._floating_timer.winfo_exists() and snap.state != TimerState.IDLE:
            self._floating_timer.update_timer(display, snap.label, urgent=urgent)

        if snap.state == TimerState.RUNNING:
            if snap.remaining_sec == 300:
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            elif snap.remaining_sec == 60:
                winsound.MessageBeep(winsound.MB_ICONHAND)

    def _on_club_finish(self, tv_id: str) -> None:
        self.after(0, lambda: self._club_finish_ui(tv_id))

    def _club_finish_ui(self, tv_id: str) -> None:
        timer = self._get_tv_timer(tv_id)
        client = self._get_tv_client(tv_id)
        tv = get_tv(self.config_data, tv_id) or {}
        if not any(t.snapshot().state == TimerState.RUNNING for t in self._tv_timers.values()):
            self._stop_club_tick_loop()
        winsound.MessageBeep(winsound.MB_ICONHAND)
        if tv_id == self._active_tv_id:
            self._update_club_ui(timer.snapshot())
        self._render_tv_list()
        self._log(f"Клуб {tv.get('name', '')}: время вышло!")

        if self._club_tv_enabled() and client.connected:
            self._run_async(
                lambda: self._sync_tv_displays_work(timer.snapshot(), start=False, client=client),
                lambda results, tid=tv_id: self._on_tv_sync(results, started=False, tv_id=tid),
            )

        if hasattr(self, "club_auto_off") and self.club_auto_off.get():
            if client.connected:
                self._run_async(
                    client.shutdown,
                    lambda r: self._log(f"Клуб {tv.get('name', '')}: TV выключен" if r.ok else f"Клуб: {r.error}"),
                )
            else:
                self._log(f"Клуб {tv.get('name', '')}: TV не подключён — выключение пропущено")
                if tv_id == self._active_tv_id:
                    messagebox.showwarning(
                        "Клуб",
                        f"Время вышло на {tv.get('name', 'TV')}, но он не подключён.\n"
                        "Подключите TV для автовыключения.",
                    )
        elif tv_id == self._active_tv_id:
            messagebox.showinfo("Клуб", f"Время сессии истекло — {tv.get('name', 'TV')}!")

    # ── TV page ───────────────────────────────────────────────────────

    def _section_label(self, parent, text: str) -> None:
        ctk.CTkLabel(
            parent,
            text=text.upper(),
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=COLORS["text_muted"],
        ).pack(anchor="w", pady=(0, 6))

    def _remote_btn(
        self,
        parent,
        text: str,
        command,
        *,
        width=72,
        height=52,
        fg_color=None,
        hover_color=None,
        font=None,
        corner_radius=12,
    ) -> ctk.CTkButton:
        return ctk.CTkButton(
            parent,
            text=text,
            width=width,
            height=height,
            corner_radius=corner_radius,
            font=ctk.CTkFont(family="Segoe UI", size=font or 13, weight="bold" if font and font >= 15 else "normal"),
            fg_color=fg_color or COLORS["btn_nav"],
            hover_color=hover_color or COLORS["btn_hover"],
            command=command,
        )

    def _set_tv_status(self, text: str, state: str = "offline") -> None:
        colors = {"online": COLORS["online"], "offline": COLORS["offline"], "connecting": COLORS["connecting"]}
        if hasattr(self, "tv_status_dot"):
            self.tv_status_dot.configure(fg_color=colors.get(state, COLORS["offline"]))
        if hasattr(self, "tv_status"):
            self.tv_status.configure(text=text, text_color=COLORS["text"])

    def _bind_tv_keys(self) -> None:
        binds = {
            "<Up>": lambda e: self._send_key("up"),
            "<Down>": lambda e: self._send_key("down"),
            "<Left>": lambda e: self._send_key("left"),
            "<Right>": lambda e: self._send_key("right"),
            "<Return>": lambda e: self._send_key("ok"),
            "<Escape>": lambda e: self._send_key("back"),
            "<Home>": lambda e: self._send_key("home"),
            "<plus>": lambda e: self._send_key("volume_up"),
            "<minus>": lambda e: self._send_key("volume_down"),
        }
        for seq, fn in binds.items():
            self.bind(seq, fn)
            self._tv_key_bind_ids.append(seq)

    def _unbind_tv_keys(self) -> None:
        for seq in self._tv_key_bind_ids:
            self.unbind(seq)
        self._tv_key_bind_ids.clear()

    def _build_tv_page(self) -> None:
        page = self._page("tv")
        page.grid_columnconfigure(0, weight=0)
        page.grid_columnconfigure(1, weight=1)

        # ── Left: connection panel
        left = ctk.CTkFrame(page, fg_color=COLORS["card"], corner_radius=16, border_width=1, border_color=COLORS["card_border"])
        left.grid(row=0, column=0, sticky="ns", padx=(4, 12), pady=4)

        ctk.CTkLabel(
            left,
            text="Подключение",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=COLORS["text"],
        ).pack(anchor="w", padx=20, pady=(20, 4))
        ctk.CTkLabel(
            left,
            text="EvoTV / Android TV\nв вашей Wi‑Fi сети",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=COLORS["text_muted"],
            justify="left",
        ).pack(anchor="w", padx=20, pady=(0, 16))

        ctk.CTkLabel(left, text="IP-адрес", font=ctk.CTkFont(size=11), text_color=COLORS["text_muted"]).pack(anchor="w", padx=20)
        self.host_entry = ctk.CTkEntry(left, width=220, height=38, placeholder_text="192.168.1.100", corner_radius=10)
        active = self._active_tv_record()
        self.host_entry.insert(0, active.get("host", self.config_data.get("host", "192.168.1.100")))
        self.host_entry.pack(padx=20, pady=(4, 12))

        ctk.CTkLabel(left, text="Порт ADB", font=ctk.CTkFont(size=11), text_color=COLORS["text_muted"]).pack(anchor="w", padx=20)
        self.port_entry = ctk.CTkEntry(left, width=220, height=38, corner_radius=10)
        self.port_entry.insert(0, str(active.get("port", self.config_data.get("port", 5555))))
        self.port_entry.pack(padx=20, pady=(4, 16))

        self.connect_btn = ctk.CTkButton(
            left,
            text="Подключиться",
            width=220,
            height=42,
            corner_radius=10,
            fg_color=COLORS["accent"],
            hover_color="#5a52e0",
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._toggle_tv_connection,
        )
        self.connect_btn.pack(padx=20, pady=(0, 12))

        power_side = ctk.CTkFrame(left, fg_color="transparent")
        power_side.pack(fill="x", padx=20, pady=(0, 16))
        ctk.CTkButton(
            power_side,
            text="⏻ Включить",
            width=105,
            height=38,
            fg_color="#2d6a4f",
            hover_color="#3d8a6f",
            command=self._tv_wake,
        ).pack(side="left", padx=(0, 6))
        ctk.CTkButton(
            power_side,
            text="⏻ Выключить",
            width=105,
            height=38,
            fg_color=COLORS["btn_power"],
            hover_color=COLORS["btn_power_hover"],
            command=self._tv_shutdown,
        ).pack(side="left")

        status_row = ctk.CTkFrame(left, fg_color=COLORS["remote_body"], corner_radius=10)
        status_row.pack(fill="x", padx=20, pady=(0, 16))
        self.tv_status_dot = ctk.CTkFrame(status_row, width=10, height=10, corner_radius=5, fg_color=COLORS["offline"])
        self.tv_status_dot.pack(side="left", padx=(14, 8), pady=14)
        self.tv_status = ctk.CTkLabel(status_row, text="Не подключено", font=ctk.CTkFont(size=12), text_color=COLORS["text"])
        self.tv_status.pack(side="left", pady=14)

        ctk.CTkFrame(left, height=1, fg_color=COLORS["card_border"]).pack(fill="x", padx=20, pady=4)

        ctk.CTkLabel(
            left,
            text="Как включить ADB:",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=COLORS["text_muted"],
        ).pack(anchor="w", padx=20, pady=(12, 6))
        for step in [
            "1. Настройки → О телевизоре",
            "2. 7× нажать «Номер сборки»",
            "3. Для разработчиков →",
            "   Отладка по USB ✓",
        ]:
            ctk.CTkLabel(left, text=step, font=ctk.CTkFont(size=11), text_color=COLORS["text_muted"], justify="left").pack(
                anchor="w", padx=20, pady=1
            )

        ctk.CTkButton(
            left,
            text="⏱ Таймер →",
            width=220,
            height=36,
            fg_color=COLORS["btn_success"],
            hover_color="#2d6a4f",
            command=lambda: self._show_page("club"),
        ).pack(padx=20, pady=(0, 8))
        ctk.CTkButton(
            left,
            text="Система TV →",
            width=220,
            height=36,
            fg_color="transparent",
            border_width=1,
            border_color=COLORS["card_border"],
            hover_color=COLORS["sidebar_hover"],
            command=lambda: self._show_page("tv_system"),
        ).pack(padx=20, pady=(20, 20))

        # ── Right: remote control
        right = ctk.CTkFrame(page, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew", pady=4)

        ctk.CTkLabel(
            right,
            text="Пульт управления",
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
            text_color=COLORS["text"],
        ).pack(anchor="w", pady=(0, 2))
        self.tv_page_subtitle = ctk.CTkLabel(
            right,
            text="",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["accent"],
        )
        self.tv_page_subtitle.pack(anchor="w", pady=(0, 2))
        ctk.CTkLabel(
            right,
            text="Стрелки на клавиатуре тоже работают  ·  Enter = OK  ·  Esc = Назад  ·  ⏱ Таймер — в боковом меню",
            font=ctk.CTkFont(size=11),
            text_color=COLORS["text_muted"],
        ).pack(anchor="w", pady=(0, 12))

        remote = ctk.CTkFrame(
            right,
            fg_color=COLORS["remote_body"],
            corner_radius=24,
            border_width=1,
            border_color=COLORS["card_border"],
        )
        remote.pack(fill="both", expand=True)

        inner = ctk.CTkFrame(remote, fg_color="transparent")
        inner.pack(padx=28, pady=24)

        # Power row
        power_row = ctk.CTkFrame(inner, fg_color="transparent")
        power_row.pack(pady=(0, 16))
        self._section_label(power_row, "Питание")
        power_btns = ctk.CTkFrame(power_row, fg_color="transparent")
        power_btns.pack()
        self._remote_btn(
            power_btns,
            "⏻\nВкл",
            self._tv_wake,
            width=88,
            height=72,
            corner_radius=16,
            fg_color="#2d6a4f",
            hover_color="#3d8a6f",
            font=14,
        ).pack(side="left", padx=10)
        self._remote_btn(
            power_btns,
            "⏻\nВыкл",
            self._tv_shutdown,
            width=88,
            height=72,
            corner_radius=16,
            fg_color=COLORS["btn_power"],
            hover_color=COLORS["btn_power_hover"],
            font=14,
        ).pack(side="left", padx=10)

        # Main remote body: volume | dpad | (empty)
        body = ctk.CTkFrame(inner, fg_color="transparent")
        body.pack()
        body.grid_columnconfigure(0, weight=0)
        body.grid_columnconfigure(1, weight=1)

        vol_col = ctk.CTkFrame(body, fg_color="transparent")
        vol_col.grid(row=0, column=0, padx=(0, 24), sticky="n")
        self._section_label(vol_col, "Громкость")
        vol_btns = ctk.CTkFrame(vol_col, fg_color="transparent")
        vol_btns.pack()
        self._remote_btn(vol_btns, "+", lambda: self._send_key("volume_up"), width=64, height=64, corner_radius=14).pack(pady=4)
        self._remote_btn(
            vol_btns, "🔇", lambda: self._send_key("mute"), width=64, height=44, fg_color=COLORS["btn_muted"]
        ).pack(pady=4)
        self._remote_btn(vol_btns, "−", lambda: self._send_key("volume_down"), width=64, height=64, corner_radius=14).pack(pady=4)

        dpad_col = ctk.CTkFrame(body, fg_color="transparent")
        dpad_col.grid(row=0, column=1, sticky="n")
        self._section_label(dpad_col, "Навигация")
        dpad = ctk.CTkFrame(dpad_col, fg_color="transparent")
        dpad.pack()
        self._remote_btn(dpad, "▲", lambda: self._send_key("up"), width=70, height=54, font=16).grid(row=0, column=1, pady=3)
        self._remote_btn(dpad, "◀", lambda: self._send_key("left"), width=70, height=54, font=16).grid(row=1, column=0, padx=3)
        self._remote_btn(
            dpad,
            "OK",
            lambda: self._send_key("ok"),
            width=88,
            height=88,
            corner_radius=44,
            fg_color=COLORS["btn_ok"],
            hover_color=COLORS["btn_ok_hover"],
            font=16,
        ).grid(row=1, column=1, padx=3)
        self._remote_btn(dpad, "▶", lambda: self._send_key("right"), width=70, height=54, font=16).grid(row=1, column=2, padx=3)
        self._remote_btn(dpad, "▼", lambda: self._send_key("down"), width=70, height=54, font=16).grid(row=2, column=1, pady=3)

        # System buttons
        sys_frame = ctk.CTkFrame(inner, fg_color="transparent")
        sys_frame.pack(pady=(20, 12))
        self._section_label(sys_frame, "Системные кнопки")
        sys_row = ctk.CTkFrame(sys_frame, fg_color="transparent")
        sys_row.pack()
        for label, key in [("Домой", "home"), ("Назад", "back"), ("Меню", "menu"), ("Поиск", "search")]:
            self._remote_btn(sys_row, label, lambda k=key: self._send_key(k), width=96, height=44, font=12).pack(
                side="left", padx=4
            )

        # Media
        media_frame = ctk.CTkFrame(inner, fg_color="transparent")
        media_frame.pack(pady=(0, 12))
        self._section_label(media_frame, "Медиа")
        media_row = ctk.CTkFrame(media_frame, fg_color="transparent")
        media_row.pack()
        for label, key in [("⏪ Назад", "rewind"), ("⏯ Пауза", "play_pause"), ("⏩ Вперёд", "forward")]:
            self._remote_btn(media_row, label, lambda k=key: self._send_key(k), width=110, height=44, font=12).pack(
                side="left", padx=4
            )

        # Quick apps
        apps_frame = ctk.CTkFrame(inner, fg_color="transparent")
        apps_frame.pack(pady=(0, 12))
        self._section_label(apps_frame, "Приложения")
        apps_row = ctk.CTkFrame(apps_frame, fg_color="transparent")
        apps_row.pack()
        for label, pkg, act in QUICK_APPS:
            fg, hov = QUICK_APP_STYLES.get(label, (COLORS["btn"], COLORS["btn_hover"]))
            ctk.CTkButton(
                apps_row,
                text=label,
                width=100,
                height=40,
                corner_radius=10,
                fg_color=fg,
                hover_color=hov,
                font=ctk.CTkFont(size=12, weight="bold"),
                command=lambda p=pkg, a=act: self._launch(p, a),
            ).pack(side="left", padx=4)

        # Bottom row: sleep + touchpad
        bottom = ctk.CTkFrame(inner, fg_color="transparent")
        bottom.pack(fill="x", pady=(4, 0))

        sleep_col = ctk.CTkFrame(bottom, fg_color="transparent")
        sleep_col.pack(side="left", padx=(0, 16))
        self._remote_btn(
            sleep_col, "💤 Сон", self._tv_sleep, width=120, height=44, fg_color=COLORS["btn_muted"]
        ).pack()
        self._remote_btn(
            sleep_col, "ℹ Инфо", self._show_tv_info, width=120, height=36, fg_color="transparent", font=11
        ).pack(pady=(6, 0))

        touch_col = ctk.CTkFrame(bottom, fg_color="transparent")
        touch_col.pack(side="left", fill="x", expand=True)
        self._section_label(touch_col, "Тачпад — клик и водите пальцем")
        touch_wrap = ctk.CTkFrame(touch_col, fg_color=COLORS["touchpad_bg"], corner_radius=12, border_width=1, border_color=COLORS["touchpad_border"])
        touch_wrap.pack(fill="x")
        self.touch_pad = tk.Canvas(
            touch_wrap,
            width=380,
            height=90,
            bg=COLORS["touchpad_bg"],
            highlightthickness=0,
            cursor="hand2",
        )
        self.touch_pad.pack(padx=8, pady=8)
        self._touch_hint = self.touch_pad.create_text(
            190, 45, text="↕  Тачпад  ↕", fill=COLORS["text_muted"], font=("Segoe UI", 11)
        )
        self.touch_pad.bind("<Button-1>", self._on_touch_click)
        self.touch_pad.bind("<B1-Motion>", self._on_touch_drag)

    # ── TV System (direct access) ─────────────────────────────────────

    def _build_tv_system_page(self) -> None:
        page = self._page("tv_system")
        ctk.CTkLabel(
            page,
            text="Система телевизора — прямой доступ",
            font=ctk.CTkFont(size=24, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=6, pady=(0, 4))
        ctk.CTkLabel(
            page,
            text="Экран TV на ПК, терминал Android, файлы и приложения через ADB",
            font=ctk.CTkFont(size=12),
            text_color="gray65",
            anchor="w",
        ).grid(row=1, column=0, sticky="w", padx=6, pady=(0, 8))

        if not self.tv_client.connected:
            warn = ctk.CTkFrame(page)
            warn.grid(row=2, column=0, sticky="ew", padx=6, pady=4)
            ctk.CTkLabel(
                warn,
                text="⚠ Сначала подключитесь к TV на вкладке «Телевизор»",
                text_color="#ffd166",
            ).pack(padx=12, pady=10, anchor="w")
            ctk.CTkButton(warn, text="Перейти к подключению", command=lambda: self._show_page("tv")).pack(
                padx=12, pady=(0, 10), anchor="w"
            )

        tabs = ctk.CTkTabview(page, height=480)
        tabs.grid(row=3, column=0, sticky="nsew", padx=6, pady=4)
        tabs.add("Экран")
        tabs.add("Терминал")
        tabs.add("Файлы")
        tabs.add("Приложения")

        # ── Screen mirror tab
        screen_tab = tabs.tab("Экран")
        screen_toolbar = ctk.CTkFrame(screen_tab, fg_color="transparent")
        screen_toolbar.pack(fill="x", pady=(4, 6))
        self.mirror_btn = ctk.CTkButton(
            screen_toolbar, text="▶ Запустить трансляцию", width=160, fg_color="#2d6a4f", command=self._toggle_mirror
        )
        self.mirror_btn.pack(side="left", padx=4)
        ctk.CTkButton(screen_toolbar, text="📷 Снимок", width=90, command=self._capture_screenshot).pack(side="left", padx=4)
        ctk.CTkButton(screen_toolbar, text="🖥 Scrcpy", width=90, command=self._launch_scrcpy).pack(side="left", padx=4)
        self.mirror_status = ctk.CTkLabel(screen_tab, text="Клик по экрану = нажатие на TV", text_color="gray60")
        self.mirror_status.pack(anchor="w", padx=4)

        mirror_frame = ctk.CTkFrame(screen_tab)
        mirror_frame.pack(fill="both", expand=True, pady=4)
        self.mirror_label = tk.Label(mirror_frame, bg="#0d0d0d", text="Трансляция экрана TV", fg="#555")
        self.mirror_label.pack(fill="both", expand=True, padx=4, pady=4)
        self.mirror_label.bind("<Button-1>", self._on_mirror_click)
        self.mirror_label.bind("<B1-Motion>", self._on_mirror_drag)
        self._mirror_drag_start = None

        # ── Terminal tab
        term_tab = tabs.tab("Терминал")
        preset_row = ctk.CTkFrame(term_tab, fg_color="transparent")
        preset_row.pack(fill="x", pady=4)
        ctk.CTkLabel(preset_row, text="Быстрые команды:").pack(side="left", padx=4)
        for label, cmd in SHELL_PRESETS:
            ctk.CTkButton(
                preset_row, text=label, width=70, height=28, command=lambda c=cmd: self._run_shell_command(c)
            ).pack(side="left", padx=2)

        self.shell_output = ctk.CTkTextbox(term_tab, height=320, font=ctk.CTkFont(family="Consolas", size=11))
        self.shell_output.pack(fill="both", expand=True, padx=4, pady=4)
        self.shell_output.insert("end", "# ADB Shell — прямой доступ к Android на TV\n# Примеры: pm list packages | grep youtube\n\n")
        self.shell_output.configure(state="disabled")

        shell_input_row = ctk.CTkFrame(term_tab, fg_color="transparent")
        shell_input_row.pack(fill="x", pady=4)
        ctk.CTkLabel(shell_input_row, text="$").pack(side="left", padx=(4, 2))
        self.shell_entry = ctk.CTkEntry(shell_input_row, placeholder_text="shell команда...")
        self.shell_entry.pack(side="left", fill="x", expand=True, padx=4)
        self.shell_entry.bind("<Return>", lambda e: self._run_shell_from_entry())
        self.shell_entry.bind("<Up>", self._shell_history_up)
        self.shell_entry.bind("<Down>", self._shell_history_down)
        ctk.CTkButton(shell_input_row, text="Выполнить", width=90, command=self._run_shell_from_entry).pack(side="right", padx=4)
        ctk.CTkButton(shell_input_row, text="Очистить", width=80, fg_color="#555", command=self._clear_shell).pack(side="right")

        # ── Files tab
        files_tab = tabs.tab("Файлы")
        path_row = ctk.CTkFrame(files_tab, fg_color="transparent")
        path_row.pack(fill="x", pady=4)
        ctk.CTkButton(path_row, text="↑", width=36, command=self._fs_go_up).pack(side="left", padx=2)
        self.fs_path_entry = ctk.CTkEntry(path_row, placeholder_text="/sdcard")
        self.fs_path_entry.insert(0, self._current_fs_path)
        self.fs_path_entry.pack(side="left", fill="x", expand=True, padx=4)
        ctk.CTkButton(path_row, text="Открыть", width=80, command=self._fs_go_to_path).pack(side="left", padx=2)
        ctk.CTkButton(path_row, text="🔄", width=36, command=self._refresh_fs_list).pack(side="left", padx=2)

        fs_actions = ctk.CTkFrame(files_tab, fg_color="transparent")
        fs_actions.pack(fill="x", pady=2)
        ctk.CTkButton(fs_actions, text="⬇ Скачать файл", command=self._fs_pull).pack(side="left", padx=4)
        ctk.CTkButton(fs_actions, text="⬆ Загрузить на TV", command=self._fs_push).pack(side="left", padx=4)
        ctk.CTkButton(fs_actions, text="📂 /sdcard", width=80, command=lambda: self._fs_navigate("/sdcard")).pack(side="left", padx=4)
        ctk.CTkButton(fs_actions, text="📂 /data", width=80, command=lambda: self._fs_navigate("/data")).pack(side="left", padx=4)

        self.fs_listbox = tk.Listbox(files_tab, height=14, bg="#1a1a1a", fg="#eee", selectbackground="#1f6aa5", font=("Consolas", 10))
        self.fs_listbox.pack(fill="both", expand=True, padx=4, pady=4)
        self.fs_listbox.bind("<Double-Button-1>", self._fs_open_selected)

        # ── Apps tab
        apps_tab = tabs.tab("Приложения")
        apps_toolbar = ctk.CTkFrame(apps_tab, fg_color="transparent")
        apps_toolbar.pack(fill="x", pady=4)
        self.apps_filter = ctk.CTkEntry(apps_toolbar, placeholder_text="Фильтр...", width=200)
        self.apps_filter.pack(side="left", padx=4)
        ctk.CTkButton(apps_toolbar, text="🔄", width=36, command=self._refresh_apps_list).pack(side="left", padx=2)
        apps_actions = ctk.CTkFrame(apps_tab, fg_color="transparent")
        apps_actions.pack(fill="x", pady=2)
        ctk.CTkButton(apps_actions, text="▶ Запустить", command=self._app_launch_selected).pack(side="left", padx=4)
        ctk.CTkButton(apps_actions, text="⏹ Остановить", fg_color="#555", command=self._app_stop_selected).pack(side="left", padx=4)
        ctk.CTkButton(apps_actions, text="🗑 Удалить", fg_color="#8b0000", command=self._app_uninstall_selected).pack(side="left", padx=4)

        self.apps_listbox = tk.Listbox(apps_tab, height=16, bg="#1a1a1a", fg="#eee", selectbackground="#1f6aa5", font=("Consolas", 10))
        self.apps_listbox.pack(fill="both", expand=True, padx=4, pady=4)

    def _toggle_mirror(self) -> None:
        if self._mirror_running:
            self._stop_mirror()
        else:
            self._start_mirror()

    def _start_mirror(self) -> None:
        if not self._require_tv():
            return
        self._screen_size = self.tv_client.get_screen_size()
        self._mirror_running = True
        self.mirror_btn.configure(text="⏹ Остановить", fg_color="#8b0000")
        self.mirror_status.configure(text=f"Трансляция {self._screen_size[0]}x{self._screen_size[1]} — клик = тап")
        self._log("TV: трансляция экрана запущена")
        self._mirror_tick()

    def _stop_mirror(self) -> None:
        self._mirror_running = False
        if self._mirror_timer:
            self.after_cancel(self._mirror_timer)
            self._mirror_timer = None
        if hasattr(self, "mirror_btn"):
            self.mirror_btn.configure(text="▶ Запустить трансляцию", fg_color="#2d6a4f")

    def _mirror_tick(self) -> None:
        if not self._mirror_running or not self.tv_client.connected:
            return

        def work():
            return self.tv_client.screencap()

        def done(data):
            if data:
                self._update_mirror_image(data)
            if self._mirror_running:
                self._mirror_timer = self.after(500, self._mirror_tick)

        self._run_async(work, done)

    def _update_mirror_image(self, png_bytes: bytes) -> None:
        try:
            img = Image.open(io.BytesIO(png_bytes))
            max_w, max_h = 640, 360
            img.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
            self._mirror_photo = ImageTk.PhotoImage(img)
            self.mirror_label.configure(image=self._mirror_photo, text="")
            self._display_size = img.size
        except Exception:
            pass

    def _mirror_coords(self, event) -> tuple[int, int]:
        sw, sh = self._screen_size
        dw = getattr(self, "_display_size", (640, 360))[0]
        dh = getattr(self, "_display_size", (640, 360))[1]
        lw = max(self.mirror_label.winfo_width(), 1)
        lh = max(self.mirror_label.winfo_height(), 1)
        ox = (lw - dw) // 2
        oy = (lh - dh) // 2
        rx = max(0, min(event.x - ox, dw))
        ry = max(0, min(event.y - oy, dh))
        return int(rx * sw / max(dw, 1)), int(ry * sh / max(dh, 1))

    def _on_mirror_click(self, event) -> None:
        if not self.tv_client.connected:
            return
        x, y = self._mirror_coords(event)
        self._run_async(lambda: self.tv_client.tap(x, y), lambda r: self._log(f"TV: тап {x},{y}"))

    def _on_mirror_drag(self, event) -> None:
        if not self.tv_client.connected:
            return
        if self._mirror_drag_start is None:
            self._mirror_drag_start = (event.x, event.y)
            return
        x1, y1 = self._mirror_drag_start
        if abs(event.x - x1) + abs(event.y - y1) < 12:
            return
        sx, sy = self._mirror_coords(type("E", (), {"x": x1, "y": y1})())
        ex, ey = self._mirror_coords(event)
        self._mirror_drag_start = (event.x, event.y)
        self._run_async(lambda: self.tv_client.swipe(sx, sy, ex, ey, 200), lambda r: None)

    def _capture_screenshot(self) -> None:
        if not self._require_tv():
            return

        def work():
            data = self.tv_client.screencap()
            if not data:
                return None
            out_dir = Path.home() / ".evo-remote" / "screenshots"
            out_dir.mkdir(parents=True, exist_ok=True)
            path = out_dir / f"tv_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            path.write_bytes(data)
            return str(path)

        def done(path):
            if path:
                self._log(f"TV: скриншот сохранён — {path}")
                messagebox.showinfo("Снимок", f"Сохранено:\n{path}")
            else:
                self._log("TV: не удалось сделать снимок")

        self._run_async(work, done)

    def _launch_scrcpy(self) -> None:
        if not self._require_tv():
            return
        host = self.config_data.get("host", "")
        port = self.config_data.get("port", 5555)
        tools = Path(__file__).parent / "tools" / "scrcpy" / "scrcpy.exe"
        scrcpy = str(tools) if tools.exists() else "scrcpy"
        try:
            subprocess.Popen(
                [scrcpy, f"--tcpip={host}:{port}", "--stay-awake"],
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            self._log(f"TV: запущен scrcpy → {host}:{port}")
        except FileNotFoundError:
            messagebox.showinfo(
                "Scrcpy",
                "Scrcpy не найден.\n\n"
                "Установите с https://github.com/Genymobile/scrcpy/releases\n"
                "или положите scrcpy.exe в папку tools/scrcpy/\n\n"
                "Пока используйте встроенную трансляцию экрана.",
            )

    def _append_shell(self, text: str) -> None:
        self.shell_output.configure(state="normal")
        self.shell_output.insert("end", text + "\n")
        self.shell_output.see("end")
        self.shell_output.configure(state="disabled")

    def _clear_shell(self) -> None:
        self.shell_output.configure(state="normal")
        self.shell_output.delete("1.0", "end")
        self.shell_output.configure(state="disabled")

    def _run_shell_from_entry(self) -> None:
        cmd = self.shell_entry.get().strip()
        if cmd:
            self._run_shell_command(cmd)

    def _run_shell_command(self, cmd: str) -> None:
        if not self._require_tv():
            return
        self.shell_entry.delete(0, "end")
        if cmd and (not self._shell_history or self._shell_history[-1] != cmd):
            self._shell_history.append(cmd)
        self._shell_hist_idx = len(self._shell_history)
        self._append_shell(f"\n$ {cmd}")

        def work():
            return self.tv_client.open_shell_session(cmd)

        def done(result):
            out = result.output if result.ok else result.error
            self._append_shell(out or "(пусто)")

        self._run_async(work, done)

    def _shell_history_up(self, _event) -> str:
        if not self._shell_history:
            return "break"
        if self._shell_hist_idx > 0:
            self._shell_hist_idx -= 1
        self.shell_entry.delete(0, "end")
        self.shell_entry.insert(0, self._shell_history[self._shell_hist_idx])
        return "break"

    def _shell_history_down(self, _event) -> str:
        if not self._shell_history:
            return "break"
        if self._shell_hist_idx < len(self._shell_history) - 1:
            self._shell_hist_idx += 1
            self.shell_entry.delete(0, "end")
            self.shell_entry.insert(0, self._shell_history[self._shell_hist_idx])
        else:
            self._shell_hist_idx = len(self._shell_history)
            self.shell_entry.delete(0, "end")
        return "break"

    def _fs_navigate(self, path: str) -> None:
        self._current_fs_path = path
        self.fs_path_entry.delete(0, "end")
        self.fs_path_entry.insert(0, path)
        self._refresh_fs_list()

    def _fs_go_up(self) -> None:
        parent = str(Path(self._current_fs_path).parent)
        if parent == ".":
            parent = "/"
        self._fs_navigate(parent)

    def _fs_go_to_path(self) -> None:
        self._fs_navigate(self.fs_path_entry.get().strip())

    def _refresh_fs_list(self) -> None:
        if not self.tv_client.connected:
            return
        path = self.fs_path_entry.get().strip() if hasattr(self, "fs_path_entry") else self._current_fs_path
        self._current_fs_path = path

        def work():
            return self.tv_client.list_dir(path)

        def done(result):
            self.fs_listbox.delete(0, "end")
            if not result.ok:
                self.fs_listbox.insert("end", f"Ошибка: {result.error}")
                return
            for line in result.output.splitlines():
                self.fs_listbox.insert("end", line)

        self._run_async(work, done)

    def _fs_selected_name(self) -> str | None:
        sel = self.fs_listbox.curselection()
        if not sel:
            return None
        line = self.fs_listbox.get(sel[0])
        parts = line.split()
        if len(parts) >= 8:
            return parts[-1]
        return None

    def _fs_open_selected(self, _event=None) -> None:
        name = self._fs_selected_name()
        if not name or name in (".", ".."):
            return
        line = self.fs_listbox.get(self.fs_listbox.curselection()[0])
        if line.startswith("d") or line.startswith("l"):
            base = self._current_fs_path.rstrip("/")
            self._fs_navigate(f"{base}/{name}")

    def _fs_pull(self) -> None:
        if not self._require_tv():
            return
        name = self._fs_selected_name()
        if not name:
            messagebox.showinfo("Файлы", "Выберите файл в списке")
            return
        line = self.fs_listbox.get(self.fs_listbox.curselection()[0])
        if line.startswith("d"):
            messagebox.showinfo("Файлы", "Выберите файл, не папку")
            return
        remote = f"{self._current_fs_path.rstrip('/')}/{name}"
        local = filedialog.asksaveasfilename(initialfile=name, title="Сохранить файл с TV")
        if not local:
            return
        self._run_async(
            lambda: self.tv_client.pull_file(remote, local),
            lambda r: self._log(r.output if r.ok else r.error),
        )

    def _fs_push(self) -> None:
        if not self._require_tv():
            return
        local = filedialog.askopenfilename(title="Файл для загрузки на TV")
        if not local:
            return
        name = Path(local).name
        remote = f"{self._current_fs_path.rstrip('/')}/{name}"
        self._run_async(
            lambda: self.tv_client.push_file(local, remote),
            lambda r: (self._log(r.output if r.ok else r.error), self._refresh_fs_list()),
        )

    def _refresh_apps_list(self) -> None:
        if not self.tv_client.connected or not hasattr(self, "apps_listbox"):
            return
        filt = self.apps_filter.get().strip() if hasattr(self, "apps_filter") else ""

        def work():
            return self.tv_client.list_packages(filt)

        def done(packages):
            self.apps_listbox.delete(0, "end")
            for pkg in packages:
                self.apps_listbox.insert("end", pkg)

        self._run_async(work, done)

    def _app_selected_package(self) -> str | None:
        sel = self.apps_listbox.curselection()
        return self.apps_listbox.get(sel[0]) if sel else None

    def _app_launch_selected(self) -> None:
        pkg = self._app_selected_package()
        if pkg and self._require_tv():
            self._run_async(
                lambda: self.tv_client.launch_app(pkg),
                lambda r: self._log(f"TV: запуск {pkg}" if r.ok else r.error),
            )

    def _app_stop_selected(self) -> None:
        pkg = self._app_selected_package()
        if pkg and self._require_tv():
            self._run_async(
                lambda: self.tv_client.force_stop(pkg),
                lambda r: self._log(f"TV: остановлен {pkg}" if r.ok else r.error),
            )

    def _app_uninstall_selected(self) -> None:
        pkg = self._app_selected_package()
        if not pkg or not self._require_tv():
            return
        if self._confirm("Удаление", f"Удалить приложение?\n{pkg}"):
            self._run_async(
                lambda: self.tv_client.uninstall_app(pkg),
                lambda r: (self._log(f"TV: удалён {pkg}" if r.ok else r.error), self._refresh_apps_list()),
            )

    # ── PC page ───────────────────────────────────────────────────────

    def _build_pc_page(self) -> None:
        page = self._page("pc")
        ctk.CTkLabel(page, text="Управление компьютером", font=ctk.CTkFont(size=24, weight="bold"), anchor="w").grid(
            row=0, column=0, sticky="w", padx=6, pady=(0, 8)
        )

        stats_body = self._card(page, "📈  Состояние системы", 1)
        self._stat_labels["pc_full"] = ctk.CTkLabel(
            stats_body, text="Загрузка...", justify="left", anchor="w", font=ctk.CTkFont(family="Consolas", size=12)
        )
        self._stat_labels["pc_full"].pack(anchor="w")
        ctk.CTkButton(stats_body, text="🔄 Обновить", width=100, command=self._refresh_stats).pack(anchor="w", pady=(8, 0))

        power_body = self._card(page, "⏻  Питание и сеанс", 2)
        delay_row = ctk.CTkFrame(power_body, fg_color="transparent")
        delay_row.pack(anchor="w", pady=(0, 8))
        ctk.CTkLabel(delay_row, text="Задержка (сек):").pack(side="left", padx=(0, 6))
        self.delay_entry = ctk.CTkEntry(delay_row, width=60)
        self.delay_entry.insert(0, str(self.config_data.get("shutdown_delay_sec", 0)))
        self.delay_entry.pack(side="left")

        grid = ctk.CTkFrame(power_body, fg_color="transparent")
        grid.pack(anchor="w")
        buttons = [
            ("⏻ Выключить", self._pc_shutdown, "#8b0000"),
            ("🔄 Перезагрузить", self._pc_restart, "#a0522d"),
            ("💤 Сон", self._pc_sleep, "#555555"),
            ("🌙 Гибернация", self._pc_hibernate, "#444444"),
            ("🔒 Блокировка", self._pc_lock, "#1f6aa5"),
            ("🚪 Выход", self._pc_logout, "#555555"),
            ("✖ Отмена", self._pc_cancel_shutdown, "#2d6a4f"),
        ]
        for i, (text, cmd, color) in enumerate(buttons):
            ctk.CTkButton(grid, text=text, width=140, fg_color=color, command=cmd).grid(
                row=i // 3, column=i % 3, padx=5, pady=5
            )

        ctk.CTkLabel(
            power_body,
            text="Примечание: включить этот же ПК из выключенного состояния нельзя — для этого используйте WoL на вкладке «Устройства».",
            wraplength=650,
            text_color="gray60",
            font=ctk.CTkFont(size=11),
            justify="left",
        ).pack(anchor="w", pady=(12, 0))

    # ── Devices (WoL) ─────────────────────────────────────────────────

    def _build_devices_page(self) -> None:
        page = self._page("devices")
        ctk.CTkLabel(page, text="Сетевые устройства", font=ctk.CTkFont(size=24, weight="bold"), anchor="w").grid(
            row=0, column=0, sticky="w", padx=6, pady=(0, 8)
        )

        wol_body = self._card(page, "🌐  Wake-on-LAN — включить ПК по сети", 1)
        ctk.CTkLabel(
            wol_body,
            text="Добавьте MAC-адрес компьютера, который нужно включать дистанционно.\n"
            "В BIOS включите Wake-on-LAN, в Windows — «Разрешить этому устройству будить компьютер».",
            wraplength=650,
            justify="left",
            text_color="gray65",
            font=ctk.CTkFont(size=11),
        ).pack(anchor="w", pady=(0, 8))

        self.wol_list = ctk.CTkFrame(wol_body, fg_color="transparent")
        self.wol_list.pack(fill="x")
        self._render_wol_devices()

        add_row = ctk.CTkFrame(wol_body, fg_color="transparent")
        add_row.pack(anchor="w", pady=(10, 0))
        ctk.CTkButton(add_row, text="+ Добавить устройство", command=self._add_wol_device).pack(side="left")

    def _render_wol_devices(self) -> None:
        for w in self.wol_list.winfo_children():
            w.destroy()
        devices = self.config_data.get("wol_devices", [])
        if not devices:
            ctk.CTkLabel(self.wol_list, text="Нет сохранённых устройств", text_color="gray60").pack(anchor="w")
            return
        for i, dev in enumerate(devices):
            row = ctk.CTkFrame(self.wol_list)
            row.pack(fill="x", pady=3)
            name = dev.get("name", "ПК")
            mac = dev.get("mac", "")
            ctk.CTkLabel(row, text=f"{name}  —  {mac}", anchor="w").pack(side="left", padx=10, pady=8)
            ctk.CTkButton(row, text="⚡ Включить", width=100, fg_color="#2d6a4f", command=lambda m=mac, n=name: self._wake_device(m, n)).pack(
                side="right", padx=4, pady=4
            )
            ctk.CTkButton(row, text="✕", width=36, fg_color="#555", command=lambda idx=i: self._remove_wol_device(idx)).pack(
                side="right", padx=4, pady=4
            )

    # ── Helpers ───────────────────────────────────────────────────────

    def _log(self, message: str) -> None:
        self.log_box.configure(state="normal")
        self.log_box.insert("end", message + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _get_delay(self) -> int:
        try:
            delay = int(self.delay_entry.get().strip())
        except (ValueError, AttributeError):
            delay = int(self.config_data.get("shutdown_delay_sec", 0))
        self.config_data["shutdown_delay_sec"] = delay
        save_config(self.config_data)
        return max(delay, 0)

    def _confirm(self, title: str, text: str) -> bool:
        return messagebox.askyesno(title, text)

    def _run_async(self, fn, on_done=None) -> None:
        def worker() -> None:
            result = fn()
            if on_done:
                self.after(0, lambda: on_done(result))

        threading.Thread(target=worker, daemon=True).start()

    def _refresh_stats(self) -> None:
        if self._stats_timer:
            self.after_cancel(self._stats_timer)
            self._stats_timer = None

        def work():
            return self.pc.get_stats()

        def done(stats):
            pc_text = (
                f"Имя: {stats.hostname}\n"
                f"ОС: {stats.os_name}\n"
                f"IP: {stats.local_ip}\n"
                f"CPU: {stats.cpu_percent:.0f}%\n"
                f"RAM: {stats.ram_used_gb:.1f} / {stats.ram_total_gb:.1f} GB ({stats.ram_percent:.0f}%)\n"
                f"Диск C: {stats.disk_used_gb:.0f} / {stats.disk_total_gb:.0f} GB ({stats.disk_percent:.0f}%)\n"
                f"Аптайм: {format_uptime(stats.uptime_seconds)}"
            )
            if "dash_pc" in self._stat_labels:
                self._stat_labels["dash_pc"].configure(text=pc_text)
            if "pc_full" in self._stat_labels:
                self._stat_labels["pc_full"].configure(text=pc_text)

            tv_lines = []
            for tv in self.config_data.get("tvs", []):
                tid = tv["id"]
                client = self._get_tv_client(tid)
                snap = self._get_tv_timer(tid).snapshot()
                st = "●" if client.connected else "○"
                tm = ""
                if snap.state in (TimerState.RUNNING, TimerState.PAUSED):
                    tm = f"  ⏱ {snap.display}"
                mark = " ←" if tid == self._active_tv_id else ""
                tv_lines.append(f"{st} {tv.get('name', 'TV')}  {tv.get('host', '')}{tm}{mark}")
            tv_text = "\n".join(tv_lines) if tv_lines else "Нет TV в списке"
            active = self._active_tv_record()
            if active and self.tv_client.connected:
                tv_text = f"Активный: {active.get('name', '')} — {self.tv_client.address}\n\n" + tv_text
            if "dash_tv" in self._stat_labels:
                self._stat_labels["dash_tv"].configure(text=tv_text)
            self._stats_timer = self.after(5000, self._refresh_stats)

        self._run_async(work, done)

    # ── PC actions ────────────────────────────────────────────────────

    def _pc_shutdown(self) -> None:
        delay = self._get_delay()
        msg = f"Выключить этот компьютер{' через ' + str(delay) + ' сек.' if delay else ' сейчас'}?"
        if self._confirm("Выключение ПК", msg):
            result = self.pc.shutdown(delay)
            self._log(result.message if result.ok else f"Ошибка: {result.message}")

    def _pc_restart(self) -> None:
        delay = self._get_delay()
        if self._confirm("Перезагрузка", f"Перезагрузить ПК{' через ' + str(delay) + ' сек.' if delay else ''}?"):
            result = self.pc.restart(delay)
            self._log(result.message if result.ok else f"Ошибка: {result.message}")

    def _pc_sleep(self) -> None:
        if self._confirm("Сон", "Перевести ПК в режим сна?"):
            result = self.pc.sleep()
            self._log(result.message if result.ok else f"Ошибка: {result.message}")

    def _pc_hibernate(self) -> None:
        if self._confirm("Гибернация", "Перевести ПК в гибернацию?"):
            result = self.pc.hibernate()
            self._log(result.message if result.ok else f"Ошибка: {result.message}")

    def _pc_lock(self) -> None:
        result = self.pc.lock()
        self._log(result.message if result.ok else f"Ошибка: {result.message}")

    def _pc_logout(self) -> None:
        if self._confirm("Выход", "Выйти из текущего сеанса Windows?"):
            result = self.pc.logout()
            self._log(result.message if result.ok else f"Ошибка: {result.message}")

    def _pc_cancel_shutdown(self) -> None:
        result = self.pc.cancel_shutdown()
        self._log(result.message if result.ok else f"Ошибка: {result.message}")

    # ── WoL ─────────────────────────────────────────────────────────

    def _add_wol_device(self) -> None:
        name = simpledialog.askstring("Устройство", "Имя (например: Игровой ПК):", parent=self)
        if not name:
            return
        mac = simpledialog.askstring("MAC-адрес", "MAC (AA:BB:CC:DD:EE:FF):", parent=self)
        if not mac:
            return
        devices = self.config_data.setdefault("wol_devices", [])
        devices.append({"name": name.strip(), "mac": mac.strip()})
        save_config(self.config_data)
        self._render_wol_devices()
        self._log(f"Добавлено устройство WoL: {name}")

    def _remove_wol_device(self, index: int) -> None:
        devices = self.config_data.get("wol_devices", [])
        if 0 <= index < len(devices):
            removed = devices.pop(index)
            save_config(self.config_data)
            self._render_wol_devices()
            self._log(f"Удалено: {removed.get('name', 'ПК')}")

    def _wake_device(self, mac: str, name: str) -> None:
        result = wol_wake(mac)
        self._log(f"{name}: {result.message}")

    # ── TV actions ──────────────────────────────────────────────────

    def _toggle_tv_connection(self) -> None:
        client = self._get_tv_client(self._active_tv_id)
        if client.connected:
            self._stop_mirror()
            client.disconnect()
            self.connect_btn.configure(text="Подключиться", fg_color=COLORS["accent"])
            self._set_tv_status("Не подключено", "offline")
            self._log(f"TV {self._active_tv_record().get('name', '')}: отключено")
            self._render_tv_list()
            return

        host = self.host_entry.get().strip()
        try:
            port = int(self.port_entry.get().strip())
        except ValueError:
            messagebox.showerror("Ошибка", "Неверный порт")
            return

        save_tv_connection(self.config_data, self._active_tv_id, host, port)
        tv = get_tv(self.config_data, self._active_tv_id)
        if tv:
            tv["host"] = host
            tv["port"] = port
        save_config(self.config_data)
        self._connect_tv_id(self._active_tv_id)

    def _require_tv(self) -> bool:
        if self.tv_client.connected:
            return True
        messagebox.showinfo("TV", "Сначала подключитесь к телевизору.")
        return False

    def _send_key(self, key: str) -> None:
        if not self._require_tv():
            return
        self._run_async(
            lambda: self.tv_client.keyevent(key),
            lambda r: self._log(f"TV: {key}" if r.ok else r.error),
        )

    def _tv_wake(self) -> None:
        def do_wake() -> None:
            self._run_async(
                self.tv_client.wake_screen,
                lambda r: self._log("TV: экран включён" if r.ok else f"TV: {r.error}"),
            )

        if self.tv_client.connected:
            do_wake()
            return
        tv = self._active_tv_record()
        name = tv.get("name", "TV")
        if messagebox.askyesno(
            "Включить TV",
            f"{name} не подключён.\n\nПодключиться по ADB и включить экран?\n"
            "(Если TV полностью выключен из розетки — нужен обычный пульт.)",
        ):
            self._connect_tv_id(self._active_tv_id, on_success=do_wake)

    def _tv_sleep(self) -> None:
        if self._require_tv() and self._confirm("TV", "Перевести EvoTV в сон?"):
            self._run_async(self.tv_client.sleep_device, lambda r: self._log("TV: сон" if r.ok else r.error))

    def _tv_shutdown(self) -> None:
        if self._require_tv() and self._confirm("TV", "Выключить телевизор?"):
            self._run_async(self.tv_client.shutdown, lambda r: self._log("TV: выключение" if r.ok else r.error))

    def _show_tv_info(self) -> None:
        if not self._require_tv():
            return
        self._run_async(
            self.tv_client.get_device_info,
            lambda info: messagebox.showinfo("TV", "\n".join(f"{k}: {v}" for k, v in info.items())),
        )

    def _launch(self, package: str, activity: str) -> None:
        if not self._require_tv():
            return
        self._run_async(
            lambda: self.tv_client.launch_app(package, activity),
            lambda r: self._log(f"TV: {package}" if r.ok else r.error),
        )

    def _on_touch_click(self, event) -> None:
        if hasattr(self, "_touch_hint"):
            try:
                self.touch_pad.delete(self._touch_hint)
                del self._touch_hint
            except Exception:
                pass
        if not self._require_tv():
            return
        x = int(event.x * 1920 / max(self.touch_pad.winfo_width(), 1))
        y = int(event.y * 1080 / max(self.touch_pad.winfo_height(), 1))
        self._run_async(lambda: self.tv_client.tap(x, y), lambda r: self._log(f"TV: тап {x},{y}"))

    def _on_touch_drag(self, event) -> None:
        if not self.tv_client.connected:
            return
        if self._drag_start is None:
            self._drag_start = (event.x, event.y)
            return
        x1, y1 = self._drag_start
        if abs(event.x - x1) + abs(event.y - y1) < 15:
            return
        w = max(self.touch_pad.winfo_width(), 1)
        h = max(self.touch_pad.winfo_height(), 1)
        sx1, sy1 = int(x1 * 1920 / w), int(y1 * 1080 / h)
        sx2, sy2 = int(event.x * 1920 / w), int(event.y * 1080 / h)
        self._drag_start = (event.x, event.y)
        self._run_async(lambda: self.tv_client.swipe(sx1, sy1, sx2, sy2, 200), lambda r: None)

    def _on_close(self) -> None:
        self._stop_club_tick_loop()
        self._unbind_tv_keys()
        self._stop_mirror()
        if self._stats_timer:
            self.after_cancel(self._stats_timer)
        for client in self._tv_clients.values():
            client.disconnect()
        self.destroy()


def main() -> None:
    app = ControlCenterApp()
    app.mainloop()


if __name__ == "__main__":
    main()
