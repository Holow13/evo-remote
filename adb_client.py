"""ADB client for EvoTV / Android TV / Google TV over Wi-Fi."""

from __future__ import annotations

import re
import shutil
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path

from adb_shell.adb_device import AdbDeviceTcp

from paths import BUNDLED_ADB_EXE
from adb_shell.auth.sign_pythonrsa import PythonRSASigner

KEYCODES = {
    "up": 19,
    "down": 20,
    "left": 21,
    "right": 22,
    "ok": 23,
    "enter": 66,
    "back": 4,
    "home": 3,
    "menu": 82,
    "power": 26,
    "sleep": 223,
    "volume_up": 24,
    "volume_down": 25,
    "mute": 164,
    "play_pause": 85,
    "rewind": 89,
    "forward": 90,
    "search": 84,
}


@dataclass
class CommandResult:
    ok: bool
    output: str
    error: str = ""


def _find_adb_exe() -> Path | None:
    local_app = Path.home() / "AppData" / "Local"
    candidates = [
        BUNDLED_ADB_EXE,
        local_app / "evo-remote" / "platform-tools" / "adb.exe",
        local_app / "Android" / "Sdk" / "platform-tools" / "adb.exe",
    ]
    for path in candidates:
        if path.exists():
            return path
    found = shutil.which("adb")
    return Path(found) if found else None


class EvoAdbClient:
    """Connects to Android device via system adb.exe or adb-shell library."""

    def __init__(self, keys_dir: Path | None = None) -> None:
        self._keys_dir = keys_dir or Path.home() / ".evo-remote" / "adb_keys"
        self._keys_dir.mkdir(parents=True, exist_ok=True)
        self._device: AdbDeviceTcp | None = None
        self._host = ""
        self._port = 5555
        self._lock = threading.Lock()
        self._adb_exe = _find_adb_exe()
        self._use_exe = self._adb_exe is not None
        self._exe_ready = False

    @property
    def connected(self) -> bool:
        if self._use_exe:
            return self._exe_ready
        return self._device is not None and self._device.available

    @property
    def address(self) -> str:
        if not self._host:
            return ""
        return f"{self._host}:{self._port}"

    def _run_adb(self, *args: str, timeout: float = 15.0) -> subprocess.CompletedProcess[str]:
        assert self._adb_exe is not None
        return subprocess.run(
            [str(self._adb_exe), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            encoding="utf-8",
            errors="replace",
        )

    def _serial(self) -> str:
        return f"{self._host}:{self._port}"

    def _device_online_via_exe(self) -> bool:
        try:
            result = self._run_adb("devices", timeout=8)
            for line in result.stdout.splitlines():
                if line.startswith(self._serial()) and "\tdevice" in line:
                    return True
            return False
        except Exception:
            return False

    def _load_signer(self) -> PythonRSASigner:
        android_dir = Path.home() / ".android"
        for base in (android_dir, self._keys_dir):
            priv = base / "adbkey"
            pub = base / "adbkey.pub"
            if priv.exists() and pub.exists():
                return PythonRSASigner(priv.read_text(encoding="utf-8"), pub.read_text(encoding="utf-8"))
        signer = PythonRSASigner.GenerateKeys(2048)
        priv = self._keys_dir / "adbkey"
        pub = self._keys_dir / "adbkey.pub"
        priv.write_text(signer.GetPrivateKey(), encoding="utf-8")
        pub.write_text(signer.GetPublicKey(), encoding="utf-8")
        return signer

    def connect(self, host: str, port: int = 5555, timeout: float = 12.0) -> CommandResult:
        self.disconnect()
        self._host = host.strip()
        self._port = port
        if self._use_exe:
            return self._connect_exe(timeout)
        return self._connect_lib(timeout)

    def _connect_exe(self, timeout: float) -> CommandResult:
        try:
            if self._device_online_via_exe():
                self._exe_ready = True
                return self._device_info_result()
            self._run_adb("connect", self._serial(), timeout=timeout)
            if not self._device_online_via_exe():
                return CommandResult(
                    False,
                    "",
                    "ADB не видит TV. В cmd выполните:\n"
                    f"  adb connect {self._serial()}\n"
                    f"  adb devices\n"
                    "Должно быть «device», не «offline».",
                )
            self._exe_ready = True
            return self._device_info_result()
        except subprocess.TimeoutExpired:
            return CommandResult(False, "", "Таймаут ADB. Проверьте, что TV включён и в сети.")
        except Exception as exc:
            return CommandResult(False, "", f"Ошибка ADB: {exc}")

    def _connect_lib(self, timeout: float) -> CommandResult:
        with self._lock:
            try:
                device = AdbDeviceTcp(self._host, self._port, default_transport_timeout_s=timeout)
                signer = self._load_signer()
                connected = device.connect(rsa_keys=[signer], auth_timeout_s=3.0)
                if not connected:
                    return CommandResult(
                        False,
                        "",
                        "Не удалось подключиться. Подтвердите отладку на TV "
                        "или используйте adb pair (ключи в %USERPROFILE%\\.android).",
                    )
                self._device = device
                return self._device_info_result()
            except TimeoutError:
                return CommandResult(False, "", "Таймаут подключения.")
            except ConnectionRefusedError:
                return CommandResult(False, "", "Соединение отклонено. Включите отладку на TV.")
            except OSError as exc:
                return CommandResult(False, "", f"Ошибка сети: {exc}")

    def _device_info_result(self) -> CommandResult:
        model = self.shell("getprop ro.product.model").output.strip()
        brand = self.shell("getprop ro.product.brand").output.strip()
        via = "adb.exe" if self._use_exe else "adb-shell"
        name = f"{brand} {model}".strip() or "Android TV"
        return CommandResult(True, f"Подключено: {name} ({via})")

    def disconnect(self) -> None:
        self._exe_ready = False
        if self._device is not None:
            try:
                self._device.close()
            except Exception:
                pass
            self._device = None

    def shell(self, command: str) -> CommandResult:
        if self._use_exe and self._exe_ready:
            return self._shell_exe(command)
        with self._lock:
            if not self.connected or self._device is None:
                return CommandResult(False, "", "Нет подключения к устройству")
            try:
                output = self._device.shell(command, timeout_s=15)
                if isinstance(output, bytes):
                    output = output.decode("utf-8", errors="replace")
                return CommandResult(True, output or "")
            except Exception as exc:
                return CommandResult(False, "", str(exc))

    def _shell_exe(self, command: str) -> CommandResult:
        try:
            result = self._run_adb("-s", self._serial(), "shell", command, timeout=20)
            if result.returncode != 0 and not result.stdout and result.stderr:
                return CommandResult(False, "", result.stderr.strip())
            out = result.stdout or result.stderr or ""
            return CommandResult(True, out)
        except subprocess.TimeoutExpired:
            return CommandResult(False, "", "Таймаут команды")
        except Exception as exc:
            return CommandResult(False, "", str(exc))

    def keyevent(self, key: str | int) -> CommandResult:
        code = KEYCODES.get(key, key) if isinstance(key, str) else key
        return self.shell(f"input keyevent {code}")

    def tap(self, x: int, y: int) -> CommandResult:
        return self.shell(f"input tap {x} {y}")

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> CommandResult:
        return self.shell(f"input swipe {x1} {y1} {x2} {y2} {duration_ms}")

    def text(self, value: str) -> CommandResult:
        escaped = value.replace(" ", "%s").replace("'", "\\'")
        return self.shell(f"input text '{escaped}'")

    def sleep_device(self) -> CommandResult:
        return self.keyevent("sleep")

    def wake_screen(self) -> CommandResult:
        """Разбудить экран TV (из сна / затемнения)."""
        r1 = self.keyevent(224)  # KEYCODE_WAKEUP
        r2 = self.keyevent(82)   # KEYCODE_MENU
        if r1.ok or r2.ok:
            return CommandResult(True, "Экран включён")
        return CommandResult(False, "", r1.error or r2.error)

    def power_toggle(self) -> CommandResult:
        return self.keyevent("power")

    def shutdown(self) -> CommandResult:
        result = self.shell("reboot -p")
        if result.ok and "not found" not in result.output.lower():
            return CommandResult(True, "Команда выключения отправлена")
        result = self.shell(
            "am start -a android.intent.action.REQUEST_SHUTDOWN "
            "-n com.android.settings/.ResetActivity"
        )
        if result.ok:
            return CommandResult(True, "Запрос на выключение отправлен")
        return self.sleep_device()

    def launch_app(self, package: str, activity: str = "") -> CommandResult:
        if activity:
            cmd = f"am start -n {package}/{activity}"
        else:
            cmd = f"monkey -p {package} -c android.intent.category.LAUNCHER 1"
        return self.shell(cmd)

    def list_packages(self, filter_text: str = "") -> list[str]:
        result = self.shell("pm list packages")
        if not result.ok:
            return []
        packages = []
        for line in result.output.splitlines():
            line = line.strip()
            if line.startswith("package:"):
                name = line.split(":", 1)[1]
                if not filter_text or filter_text.lower() in name.lower():
                    packages.append(name)
        return sorted(packages)

    def get_device_info(self) -> dict[str, str]:
        props = {
            "model": "getprop ro.product.model",
            "brand": "getprop ro.product.brand",
            "android": "getprop ro.build.version.release",
            "ip": "getprop dhcp.wlan0.ipaddress",
            "sdk": "getprop ro.build.version.sdk",
            "serial": "getprop ro.serialno",
        }
        info = {}
        for key, cmd in props.items():
            res = self.shell(cmd)
            info[key] = res.output.strip() if res.ok else "—"
        return info

    def get_screen_size(self) -> tuple[int, int]:
        res = self.shell("wm size")
        if not res.ok:
            return 1920, 1080
        match = re.search(r"(\d+)x(\d+)", res.output)
        if match:
            return int(match.group(1)), int(match.group(2))
        return 1920, 1080

    def screencap(self) -> bytes | None:
        if self._use_exe and self._exe_ready:
            return self._screencap_exe()
        with self._lock:
            if not self.connected or self._device is None:
                return None
            try:
                data = self._device.shell("screencap -p", decode=False, timeout_s=20)
                if not data:
                    return None
                if isinstance(data, str):
                    data = data.encode("latin-1")
                if b"\r\n" in data:
                    data = data.replace(b"\r\n", b"\n")
                if not data.startswith(b"\x89PNG"):
                    return None
                return data
            except Exception:
                return None

    def _screencap_exe(self) -> bytes | None:
        try:
            assert self._adb_exe is not None
            result = subprocess.run(
                [str(self._adb_exe), "-s", self._serial(), "exec-out", "screencap", "-p"],
                capture_output=True,
                timeout=25,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            data = result.stdout
            if b"\r\n" in data:
                data = data.replace(b"\r\n", b"\n")
            if data.startswith(b"\x89PNG"):
                return data
            return None
        except Exception:
            return None

    def list_dir(self, path: str = "/sdcard") -> CommandResult:
        path = path.strip() or "/sdcard"
        res = self.shell(f"ls -la {self._quote(path)}")
        if res.ok and res.output.strip():
            return res
        return self.shell(f"ls -la {self._quote(path)}/")

    def read_file_head(self, path: str, lines: int = 50) -> CommandResult:
        return self.shell(f"head -n {lines} {self._quote(path)}")

    def pull_file(self, remote_path: str, local_path: str) -> CommandResult:
        if self._use_exe and self._exe_ready:
            try:
                result = self._run_adb("-s", self._serial(), "pull", remote_path, local_path, timeout=120)
                if result.returncode == 0:
                    return CommandResult(True, f"Сохранено: {local_path}")
                return CommandResult(False, "", result.stderr.strip() or "Ошибка pull")
            except Exception as exc:
                return CommandResult(False, "", str(exc))
        with self._lock:
            if not self.connected or self._device is None:
                return CommandResult(False, "", "Нет подключения")
            try:
                self._device.pull(remote_path, local_path)
                return CommandResult(True, f"Сохранено: {local_path}")
            except Exception as exc:
                return CommandResult(False, "", str(exc))

    def push_file(self, local_path: str, remote_path: str) -> CommandResult:
        if self._use_exe and self._exe_ready:
            try:
                result = self._run_adb("-s", self._serial(), "push", local_path, remote_path, timeout=120)
                if result.returncode == 0:
                    return CommandResult(True, f"Загружено на TV: {remote_path}")
                return CommandResult(False, "", result.stderr.strip() or "Ошибка push")
            except Exception as exc:
                return CommandResult(False, "", str(exc))
        with self._lock:
            if not self.connected or self._device is None:
                return CommandResult(False, "", "Нет подключения")
            try:
                self._device.push(local_path, remote_path)
                return CommandResult(True, f"Загружено на TV: {remote_path}")
            except Exception as exc:
                return CommandResult(False, "", str(exc))

    def uninstall_app(self, package: str) -> CommandResult:
        return self.shell(f"pm uninstall --user 0 {package}")

    def force_stop(self, package: str) -> CommandResult:
        return self.shell(f"am force-stop {package}")

    def open_shell_session(self, command: str) -> CommandResult:
        return self.shell(command)

    @staticmethod
    def _quote(path: str) -> str:
        return "'" + path.replace("'", "'\\''") + "'"
