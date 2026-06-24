"""Wake-on-LAN for remote PCs on the network."""

from __future__ import annotations

import re
import socket
from dataclasses import dataclass


@dataclass
class WolResult:
    ok: bool
    message: str


def normalize_mac(mac: str) -> str | None:
    cleaned = re.sub(r"[^0-9a-fA-F]", "", mac)
    if len(cleaned) != 12:
        return None
    return cleaned.lower()


def wake(mac: str, broadcast: str = "255.255.255.255") -> WolResult:
    normalized = normalize_mac(mac)
    if not normalized:
        return WolResult(False, "Неверный MAC-адрес (нужен формат AA:BB:CC:DD:EE:FF)")

    packet = bytes.fromhex("FF" * 6 + normalized * 16)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            for port in (9, 7, 2304):
                sock.sendto(packet, (broadcast, port))
        return WolResult(True, f"Magic Packet отправлен на {mac}")
    except OSError as exc:
        return WolResult(False, str(exc))
