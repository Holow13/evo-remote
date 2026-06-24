"""Список телевизоров клуба — конфиг и миграция."""

from __future__ import annotations

import uuid
from typing import Any


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


def make_tv(
    *,
    name: str,
    host: str,
    port: int = 5555,
    club_label: str = "",
    tv_id: str | None = None,
) -> dict[str, Any]:
    return {
        "id": tv_id or _new_id(),
        "name": name.strip() or "TV",
        "host": host.strip(),
        "port": int(port),
        "club_label": club_label.strip(),
    }


def normalize_config(data: dict[str, Any]) -> dict[str, Any]:
    """Миграция старого host/port → список tvs."""
    if data.get("tvs"):
        tvs = list(data["tvs"])
        for tv in tvs:
            tv.setdefault("id", _new_id())
            tv.setdefault("name", "TV")
            tv.setdefault("host", "192.168.1.100")
            tv.setdefault("port", 5555)
            tv.setdefault("club_label", data.get("club_label", "ПК-1"))
        data["tvs"] = tvs
        if not data.get("active_tv_id") or not any(t["id"] == data["active_tv_id"] for t in tvs):
            data["active_tv_id"] = tvs[0]["id"]
        return data

    host = str(data.get("host", "192.168.1.100"))
    port = int(data.get("port", 5555))
    label = str(data.get("club_label", "ПК-1"))
    tv = make_tv(name="TV-1", host=host, port=port, club_label=label, tv_id="tv1")
    data["tvs"] = [tv]
    data["active_tv_id"] = tv["id"]
    return data


def get_tv(data: dict[str, Any], tv_id: str | None = None) -> dict[str, Any] | None:
    tid = tv_id or data.get("active_tv_id")
    for tv in data.get("tvs", []):
        if tv.get("id") == tid:
            return tv
    tvs = data.get("tvs", [])
    return tvs[0] if tvs else None


def save_tv_connection(data: dict[str, Any], tv_id: str, host: str, port: int) -> None:
    tv = get_tv(data, tv_id)
    if tv:
        tv["host"] = host.strip()
        tv["port"] = int(port)
    data["host"] = host.strip()
    data["port"] = int(port)
