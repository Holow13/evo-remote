"""Пути относительно корня проекта (работает после git clone на любом ПК)."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
ADB_DIR = PROJECT_ROOT / "adb"
BUNDLED_ADB_EXE = ADB_DIR / "adb.exe"
