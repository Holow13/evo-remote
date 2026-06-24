"""Local Windows PC power control and system monitoring."""

from __future__ import annotations

import ctypes
import os
import platform
import socket
import subprocess
import time
from dataclasses import dataclass

try:
    import psutil
except ImportError:
    psutil = None  # type: ignore[assignment]


@dataclass
class ActionResult:
    ok: bool
    message: str


@dataclass
class SystemStats:
    hostname: str
    os_name: str
    cpu_percent: float
    ram_used_gb: float
    ram_total_gb: float
    ram_percent: float
    disk_used_gb: float
    disk_total_gb: float
    disk_percent: float
    uptime_seconds: float
    local_ip: str


class PCController:
    """Power and session controls for the local Windows machine."""

    def shutdown(self, delay_sec: int = 0) -> ActionResult:
        return self._run_shutdown("/s", delay_sec, "Выключение")

    def restart(self, delay_sec: int = 0) -> ActionResult:
        return self._run_shutdown("/r", delay_sec, "Перезагрузка")

    def sleep(self) -> ActionResult:
        try:
            ctypes.windll.powrprof.SetSuspendState(False, True, False)
            return ActionResult(True, "Режим сна")
        except Exception as exc:
            return ActionResult(False, str(exc))

    def hibernate(self) -> ActionResult:
        try:
            subprocess.run(["shutdown", "/h"], check=True, creationflags=_no_window())
            return ActionResult(True, "Гибернация")
        except Exception as exc:
            return ActionResult(False, str(exc))

    def lock(self) -> ActionResult:
        try:
            subprocess.run(
                ["rundll32.exe", "user32.dll,LockWorkStation"],
                check=True,
                creationflags=_no_window(),
            )
            return ActionResult(True, "Экран заблокирован")
        except Exception as exc:
            return ActionResult(False, str(exc))

    def cancel_shutdown(self) -> ActionResult:
        try:
            subprocess.run(["shutdown", "/a"], check=True, creationflags=_no_window())
            return ActionResult(True, "Выключение отменено")
        except Exception as exc:
            return ActionResult(False, str(exc))

    def logout(self) -> ActionResult:
        return self._run_shutdown("/l", 0, "Выход из сеанса")

    def get_stats(self) -> SystemStats:
        hostname = socket.gethostname()
        os_name = f"{platform.system()} {platform.release()}"
        local_ip = _local_ip()

        if psutil is None:
            return SystemStats(
                hostname=hostname,
                os_name=os_name,
                cpu_percent=0,
                ram_used_gb=0,
                ram_total_gb=0,
                ram_percent=0,
                disk_used_gb=0,
                disk_total_gb=0,
                disk_percent=0,
                uptime_seconds=0,
                local_ip=local_ip,
            )

        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("C:\\")
        return SystemStats(
            hostname=hostname,
            os_name=os_name,
            cpu_percent=psutil.cpu_percent(interval=0.1),
            ram_used_gb=mem.used / (1024**3),
            ram_total_gb=mem.total / (1024**3),
            ram_percent=mem.percent,
            disk_used_gb=disk.used / (1024**3),
            disk_total_gb=disk.total / (1024**3),
            disk_percent=disk.percent,
            uptime_seconds=time.time() - psutil.boot_time(),
            local_ip=local_ip,
        )

    def _run_shutdown(self, flag: str, delay_sec: int, label: str) -> ActionResult:
        try:
            args = ["shutdown", flag, "/t", str(max(delay_sec, 0))]
            subprocess.run(args, check=True, creationflags=_no_window())
            if delay_sec > 0:
                return ActionResult(True, f"{label} через {delay_sec} сек.")
            return ActionResult(True, f"{label} запущено")
        except Exception as exc:
            return ActionResult(False, str(exc))


def _no_window() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return "—"


def format_uptime(seconds: float) -> str:
    seconds = int(seconds)
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}д")
    if hours or days:
        parts.append(f"{hours}ч")
    parts.append(f"{minutes}м")
    return " ".join(parts)
