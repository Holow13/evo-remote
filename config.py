import json
from pathlib import Path

from tv_registry import normalize_config

CONFIG_DIR = Path.home() / ".evo-remote"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_CONFIG = {
    "host": "192.168.1.100",
    "port": 5555,
    "tvs": [],
    "active_tv_id": "",
    "last_apps": [],
    "wol_devices": [],
    "shutdown_delay_sec": 0,
    "club_label": "ПК-1",
    "club_default_minutes": 60,
    "club_auto_tv_off": True,
    "club_tv_corner_overlay": True,
    "club_show_on_tv": False,
    "club_show_floating": False,
}


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        return normalize_config(DEFAULT_CONFIG.copy())
    try:
        with CONFIG_FILE.open(encoding="utf-8") as f:
            data = json.load(f)
        merged = DEFAULT_CONFIG.copy()
        merged.update(data)
        return normalize_config(merged)
    except (json.JSONDecodeError, OSError):
        return normalize_config(DEFAULT_CONFIG.copy())


def save_config(config: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with CONFIG_FILE.open("w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
