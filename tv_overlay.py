"""Android overlay timer in top-right corner (works over HDMI on supported TVs)."""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from adb_client import CommandResult, EvoAdbClient
    from club_timer import TimerSnapshot, TimerState

OVERLAY_PKG = "com.evo.remote.timeroverlay"
OVERLAY_SERVICE = f"{OVERLAY_PKG}/.OverlayService"
APK_PATH = Path(__file__).resolve().parent / "overlay-app" / "app" / "build" / "outputs" / "apk" / "debug" / "app-debug.apk"
ACTION_UPDATE = "com.evo.remote.TIMER_UPDATE"
ACTION_HIDE = "com.evo.remote.TIMER_HIDE"


def _quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def is_overlay_installed(client: "EvoAdbClient") -> bool:
    result = client.shell(f"pm path {OVERLAY_PKG}")
    return result.ok and "package:" in result.output


def install_overlay_apk(client: "EvoAdbClient") -> "CommandResult":
    from adb_client import CommandResult

    if not APK_PATH.exists():
        return CommandResult(
            False,
            "",
            f"APK не найден: {APK_PATH}\nЗапустите build_overlay.bat на ПК.",
        )
    if client._use_exe and client._adb_exe:  # noqa: SLF001
        import subprocess

        try:
            result = subprocess.run(
                [str(client._adb_exe), "-s", client._serial(), "install", "-r", str(APK_PATH)],
                capture_output=True,
                text=True,
                timeout=120,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                encoding="utf-8",
                errors="replace",
            )
            if result.returncode == 0 and "Success" in (result.stdout or ""):
                return CommandResult(True, "Оверлей установлен на TV")
            return CommandResult(False, "", (result.stderr or result.stdout or "Ошибка install").strip())
        except Exception as exc:
            return CommandResult(False, "", str(exc))
    return CommandResult(False, "", "Нужен adb.exe для установки APK")


def grant_overlay_permission(client: "EvoAdbClient") -> None:
    client.shell(f"appops set {OVERLAY_PKG} SYSTEM_ALERT_WINDOW allow")


def ensure_overlay_ready(client: "EvoAdbClient") -> tuple[bool, str]:
    if not client.connected:
        return False, "TV не подключён"
    if not is_overlay_installed(client):
        install = install_overlay_apk(client)
        if not install.ok:
            return False, install.error
    grant_overlay_permission(client)
    return True, "ok"


def _extras_for_snapshot(snap: "TimerSnapshot") -> dict[str, str | int]:
    from club_timer import TimerState

    end_at = 0
    paused_left = 0
    if snap.state == TimerState.RUNNING:
        end_at = int((time.time() + snap.remaining_sec) * 1000)
    elif snap.state == TimerState.PAUSED:
        paused_left = snap.remaining_sec

    return {
        "state": snap.state.value,
        "label": snap.label or "Сессия",
        "endAt": end_at,
        "pausedLeft": paused_left,
    }


def _service_cmd(action: str, extras: dict[str, str | int] | None = None) -> str:
    parts = [
        "am start-foreground-service",
        f"-n {OVERLAY_SERVICE}",
        f"-a {action}",
    ]
    if extras:
        parts.append(f"--es state {extras['state']}")
        parts.append(f"--es label {_quote(str(extras['label']))}")
        parts.append(f"--el endAt {extras['endAt']}")
        parts.append(f"--ei pausedLeft {extras['pausedLeft']}")
    return " ".join(parts)


def push_overlay_timer(client: "EvoAdbClient", snap: "TimerSnapshot") -> tuple[bool, str]:
    ready, msg = ensure_overlay_ready(client)
    if not ready:
        return False, msg

    client.shell("input keyevent 224")
    extras = _extras_for_snapshot(snap)
    result = client.shell(_service_cmd(ACTION_UPDATE, extras))
    out = (result.output or result.error or "").strip()
    if result.ok and "Error" not in out:
        return True, out or "timer pushed"
    return False, out or "service start failed"


def hide_overlay_timer(client: "EvoAdbClient") -> None:
    if not client.connected:
        return
    client.shell(_service_cmd(ACTION_HIDE))
    client.shell(f"am force-stop {OVERLAY_PKG}")


def show_overlay_on_tv(
    client: "EvoAdbClient",
    snap: "TimerSnapshot",
    *,
    start_service: bool,
) -> tuple[bool, str]:
    del start_service
    return push_overlay_timer(client, snap)
