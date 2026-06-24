"""Установка окружения Control Center: Python-пакеты, ADB platform-tools."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCAL_DOWNLOADS = ROOT / "downloads"
REQUIREMENTS = ROOT / "requirements.txt"
APK_PATH = ROOT / "overlay-app" / "app" / "build" / "outputs" / "apk" / "debug" / "app-debug.apk"

PLATFORM_TOOLS_URLS = [
    "https://dl.google.com/android/repository/platform-tools-latest-windows.zip",
    "https://mirrors.cloud.tencent.com/AndroidSDK/platform-tools-latest-windows.zip",
]

ADB_LOCATIONS = [
    Path("C:/adb"),
    Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "evo-remote" / "platform-tools",
]


def log(msg: str) -> None:
    print(msg, flush=True)


def find_local_platform_tools_zip() -> Path | None:
    if not LOCAL_DOWNLOADS.is_dir():
        return None
    for path in sorted(LOCAL_DOWNLOADS.iterdir()):
        if not path.is_file():
            continue
        name = path.name.lower()
        if "platform-tools" in name and name.endswith(".zip"):
            return path
    return None


def pick_adb_dir() -> Path:
    for base in ADB_LOCATIONS:
        if (base / "adb.exe").exists():
            return base
    for base in ADB_LOCATIONS:
        try:
            base.mkdir(parents=True, exist_ok=True)
            test = base / ".write_test"
            test.write_text("ok", encoding="utf-8")
            test.unlink()
            return base
        except OSError:
            continue
    return ADB_LOCATIONS[-1]


def download_platform_tools_zip(dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    last_err = ""
    for url in PLATFORM_TOOLS_URLS:
        log(f"  Скачивание: {url}")
        try:
            urllib.request.urlretrieve(url, dest)  # noqa: S310
            if dest.stat().st_size > 100_000:
                return dest
        except Exception as exc:
            last_err = str(exc)
            log(f"  Не удалось: {exc}")
    raise RuntimeError(
        f"Не удалось скачать platform-tools.\n"
        f"Положите zip в {LOCAL_DOWNLOADS}\\ (см. downloads\\README.txt)\n"
        f"{last_err}"
    )


def extract_platform_tools(zip_path: Path, dest_dir: Path) -> None:
    log(f"  Распаковка в {dest_dir} ...")
    staging = dest_dir.parent / "_platform_tools_staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(staging)
    src = staging / "platform-tools"
    if not src.is_dir():
        src = staging
    dest_dir.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        target = dest_dir / item.name
        if item.is_dir():
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)
    shutil.rmtree(staging, ignore_errors=True)


def install_adb() -> Path:
    log("\n[2/3] Android platform-tools (adb.exe)")
    dest_dir = pick_adb_dir()
    adb_exe = dest_dir / "adb.exe"
    if adb_exe.exists():
        log(f"  OK — уже установлено: {adb_exe}")
        return adb_exe

    zip_path = find_local_platform_tools_zip()
    cache_zip = Path(os.environ.get("LOCALAPPDATA", "")) / "evo-remote" / "platform-tools-latest-windows.zip"
    if zip_path:
        log(f"  Локальный файл: {zip_path.name}")
    else:
        log("  Загрузка с интернета (≈5 МБ)...")
        zip_path = cache_zip
        download_platform_tools_zip(zip_path)

    extract_platform_tools(zip_path, dest_dir)
    if not adb_exe.exists():
        raise RuntimeError(f"adb.exe не найден после распаковки в {dest_dir}")

    log(f"  OK — {adb_exe}")
    try:
        result = subprocess.run(
            [str(adb_exe), "version"],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        ver = (result.stdout or result.stderr or "").strip().splitlines()
        if ver:
            log(f"  {ver[0]}")
    except Exception as exc:
        log(f"  Проверка версии: {exc}")

    return adb_exe


def add_to_user_path(directory: Path) -> None:
    try:
        import winreg
    except ImportError:
        return
    dir_str = str(directory.resolve())
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0, winreg.KEY_READ | winreg.KEY_WRITE)
    try:
        path, _ = winreg.QueryValueEx(key, "Path")
    except OSError:
        path = ""
    parts = [p for p in path.split(";") if p]
    if any(p.lower() == dir_str.lower() for p in parts):
        log(f"  PATH уже содержит {dir_str}")
        return
    parts.append(dir_str)
    winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, ";".join(parts))
    log(f"  Добавлено в PATH пользователя: {dir_str}")
    log("  (Перезапустите терминал / Control Center, чтобы PATH обновился)")


def install_python_packages() -> None:
    log("\n[1/3] Python-зависимости")
    if not REQUIREMENTS.exists():
        log("  requirements.txt не найден — пропуск")
        return
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", str(REQUIREMENTS), "-q"],
        check=True,
        cwd=ROOT,
    )
    log("  OK — customtkinter, adb-shell, Pillow, psutil ...")


def check_overlay_apk() -> None:
    log("\n[3/3] Проверка компонентов")
    if APK_PATH.exists():
        log(f"  OK — overlay APK: {APK_PATH.name}")
    else:
        log("  Overlay APK не собран (таймер в углу TV).")
        log("  После подключения TV: build_overlay.bat")
        log("  Или положите файлы в downloads\\ — см. OVERLAY_DOWNLOADS.txt")


def print_summary(adb_exe: Path) -> None:
    log("\n========================================")
    log("  Установка завершена")
    log("========================================")
    log(f"  ADB:     {adb_exe}")
    log(f"  Запуск:  start.bat")
    log("  TV:      Настройки → Для разработчиков → Отладка по Wi‑Fi")
    log("           adb connect IP:5555")
    if not APK_PATH.exists():
        log("  Таймер:  build_overlay.bat → install_overlay.bat")
    log("")


def main() -> int:
    log("Control Center — установка окружения")
    log(f"Папка: {ROOT}\n")
    try:
        install_python_packages()
        adb_exe = install_adb()
        add_to_user_path(adb_exe.parent)
        check_overlay_apk()
        print_summary(adb_exe)
        return 0
    except subprocess.CalledProcessError:
        log("\nОшибка pip. Запустите вручную:")
        log(f"  {sys.executable} -m pip install -r requirements.txt")
        return 1
    except Exception as exc:
        log(f"\nОШИБКА: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
