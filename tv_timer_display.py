"""Fullscreen club timer on TV via data: URI (no files, no network)."""

from __future__ import annotations

import base64
import json
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from adb_client import EvoAdbClient
    from club_timer import TimerSnapshot

_VIEWER_CANDIDATES = (
    "com.yandex.browser.tv/.tvactivity.TvActivity",
    "com.android.chrome/com.google.android.apps.chrome.Main",
    "com.android.chrome/com.google.android.apps.chrome.IntentDispatcher",
    "com.android.browser/.BrowserActivity",
)


def _intent_launched(output: str) -> bool:
    text = (output or "").strip().lower()
    if not text:
        return False
    if "error" in text and ("activity" in text or "unable" in text or "exception" in text):
        if "delivered to currently running" not in text:
            return False
    if "exception" in text and "delivered" not in text:
        return False
    return "starting:" in text or "delivered to currently running" in text


def _is_stub_component(text: str) -> bool:
    low = text.lower()
    return "stub" in low or "frameworkpackage" in low


def _installed_viewers(client: "EvoAdbClient") -> list[str]:
    found: list[str] = []
    for component in _VIEWER_CANDIDATES:
        pkg = component.split("/", 1)[0]
        check = client.shell(f"pm path {pkg}")
        if check.ok and "package:" in check.output:
            found.append(component)
    return found


def _escape_js(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def build_timer_html(snap: "TimerSnapshot") -> str:
    from club_timer import TimerState

    label = snap.label or "Сессия"
    state = snap.state.value
    end_at_ms = 0
    paused_left = 0

    if snap.state == TimerState.RUNNING:
        end_at_ms = int((time.time() + snap.remaining_sec) * 1000)
    elif snap.state == TimerState.PAUSED:
        paused_left = snap.remaining_sec

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Клуб · Таймер</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:100%;height:100%;background:#050508;overflow:hidden;font-family:sans-serif}}
.wrap{{display:flex;flex-direction:column;align-items:center;justify-content:center;height:100vh}}
.tag{{font-size:2.2vw;font-weight:700;color:#5a5a72;letter-spacing:.35em;margin-bottom:1.5vh}}
.label{{font-size:3.8vw;color:#b0b0c8;margin-bottom:3vh;text-align:center}}
.time{{font-size:20vw;font-weight:800;color:#3ddc84;line-height:1;font-variant-numeric:tabular-nums}}
.time.u{{color:#ff5252;animation:p 1.2s ease-in-out infinite}}
.time.f{{font-size:9vw;color:#ff5252}}
.time.p{{color:#f0b429}}
.status{{font-size:2vw;color:#6a6a82;margin-top:4vh}}
@keyframes p{{0%,100%{{opacity:1}}50%{{opacity:.75}}}}
</style>
</head>
<body>
<div class="wrap">
<div class="tag">КЛУБ · ТАЙМЕР</div>
<div class="label" id="l"></div>
<div class="time" id="t">00:00</div>
<div class="status" id="s"></div>
</div>
<script>
const S={_escape_js(state)},E={end_at_ms},P={paused_left},L={_escape_js(label)};
function f(x){{x=Math.max(0,x|0);const h=Math.floor(x/3600),m=Math.floor((x%3600)/60),s=x%60;
return h?String(h).padStart(2,"0")+":"+String(m).padStart(2,"0")+":"+String(s).padStart(2,"0")
:String(m).padStart(2,"0")+":"+String(s).padStart(2,"0");}}
function tick(){{
const t=document.getElementById("t"),s=document.getElementById("s");
document.getElementById("l").textContent=L;t.className="time";
if(S==="finished"){{t.textContent="ВРЕМЯ ВЫШЛО";t.classList.add("u","f");s.textContent="Сессия завершена";return;}}
if(S==="idle"){{t.textContent="—:—";s.textContent="Таймер не запущен";return;}}
let left; if(S==="paused"){{left=P;t.classList.add("p");s.textContent="Пауза";}}
else{{left=Math.max(0,Math.floor((E-Date.now())/1000));s.textContent="Осталось времени";}}
t.textContent=f(left);if(S==="running"&&left<=300&&left>0)t.classList.add("u");}}
setInterval(tick,250);tick();
</script>
</body>
</html>"""


def _wake_screen(client: "EvoAdbClient") -> None:
    client.shell("input keyevent 224")
    client.shell("input keyevent 82")


def _data_uri(html: str) -> str:
    b64 = base64.b64encode(html.encode("utf-8")).decode("ascii")
    return f"data:text/html;charset=utf-8;base64,{b64}"


def _launch_data_page(client: "EvoAdbClient", html: str) -> tuple[bool, str]:
    page_url = _data_uri(html)
    flags = "0x14000000"  # NEW_TASK | CLEAR_TOP
    safe = page_url.replace('"', "").replace("'", "")

    for pkg in {c.split("/", 1)[0] for c in _installed_viewers(client)}:
        client.shell(f"am force-stop {pkg}")

    attempts: list[str] = []
    for component in _installed_viewers(client):
        attempts.append(
            f'am start -a android.intent.action.VIEW -n {component} -d "{safe}" -f {flags}'
        )
    attempts.append(f'am start -a android.intent.action.VIEW -d "{safe}" -f {flags}')

    last_out = ""
    for cmd in attempts:
        result = client.shell(cmd)
        last_out = (result.output or result.error or "").strip()
        if _intent_launched(last_out) and not _is_stub_component(last_out):
            return True, last_out
    return False, last_out or "Не удалось открыть браузер на TV"


def show_timer_on_tv(client: "EvoAdbClient", snap: "TimerSnapshot", *, open_browser: bool) -> tuple[bool, str]:
    if not open_browser:
        return True, "ok"
    if not client.connected:
        return False, "Нет подключения к TV"

    _wake_screen(client)
    html = build_timer_html(snap)
    ok, detail = _launch_data_page(client, html)
    if ok:
        return True, detail
    return False, f"{detail}\n(страница встроена в браузер, файлы и сеть не нужны)"


def dismiss_tv_timer(client: "EvoAdbClient") -> None:
    if not client.connected:
        return
    client.keyevent("home")
