"""Club session timer — countdown and TV shutdown."""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable


class TimerState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    FINISHED = "finished"


@dataclass
class TimerSnapshot:
    state: TimerState
    total_sec: int
    remaining_sec: int
    label: str

    @property
    def display(self) -> str:
        r = max(0, self.remaining_sec)
        h, rem = divmod(r, 3600)
        m, s = divmod(rem, 60)
        if h:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"


def format_duration_for_input(total_sec: int) -> str:
    """Строка для поля ввода (MM:SS или H:MM:SS)."""
    total_sec = max(0, total_sec)
    h, rem = divmod(total_sec, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def parse_time_input(text: str) -> int | None:
    """Разбор ввода → секунды. 60 | 90:00 | 1:30:00"""
    text = text.strip().replace(",", ".")
    if not text:
        return None
    if ":" not in text:
        try:
            if "." in text:
                return max(1, int(float(text) * 60))
            return max(1, int(text)) * 60
        except ValueError:
            return None
    parts = text.split(":")
    if len(parts) < 2 or len(parts) > 3:
        return None
    try:
        nums = [int(p.strip()) for p in parts]
    except ValueError:
        return None
    if any(n < 0 for n in nums):
        return None
    if len(nums) == 2:
        m, s = nums
        if s >= 60:
            return None
        return max(1, m * 60 + s)
    h, m, s = nums
    if m >= 60 or s >= 60:
        return None
    return max(1, h * 3600 + m * 60 + s)


class ClubTimer:
    def __init__(self) -> None:
        self._total = 0
        self._remaining = 0.0
        self._state = TimerState.IDLE
        self._label = ""
        self._end_at: float | None = None
        self._on_tick: Callable[[TimerSnapshot], None] | None = None
        self._on_finish: Callable[[], None] | None = None
        self._warned_5 = False
        self._warned_1 = False

    def set_callbacks(
        self,
        on_tick: Callable[[TimerSnapshot], None] | None = None,
        on_finish: Callable[[], None] | None = None,
    ) -> None:
        self._on_tick = on_tick
        self._on_finish = on_finish

    def snapshot(self) -> TimerSnapshot:
        if self._state == TimerState.RUNNING and self._end_at is not None:
            self._remaining = max(0.0, self._end_at - time.time())
        return TimerSnapshot(
            state=self._state,
            total_sec=self._total,
            remaining_sec=int(self._remaining),
            label=self._label,
        )

    def start(self, minutes: int, label: str = "Сессия") -> None:
        self.start_seconds(max(1, minutes) * 60, label)

    def start_seconds(self, total_sec: int, label: str = "Сессия") -> None:
        self._total = max(1, total_sec)
        self._remaining = float(self._total)
        self._label = label
        self._state = TimerState.RUNNING
        self._end_at = time.time() + self._remaining
        self._warned_5 = False
        self._warned_1 = False
        self._emit()

    def pause(self) -> None:
        if self._state != TimerState.RUNNING:
            return
        self._remaining = max(0.0, (self._end_at or time.time()) - time.time())
        self._state = TimerState.PAUSED
        self._end_at = None
        self._emit()

    def resume(self) -> None:
        if self._state != TimerState.PAUSED:
            return
        self._state = TimerState.RUNNING
        self._end_at = time.time() + self._remaining
        self._emit()

    def add_minutes(self, minutes: int) -> None:
        add = max(0, minutes) * 60
        self._remaining += add
        self._total += add
        if self._state == TimerState.RUNNING:
            self._end_at = (self._end_at or time.time()) + add
        self._emit()

    def stop(self) -> None:
        self._state = TimerState.IDLE
        self._remaining = 0
        self._total = 0
        self._end_at = None
        self._label = ""
        self._emit()

    def tick(self) -> bool:
        """Returns True if timer finished this tick."""
        if self._state != TimerState.RUNNING or self._end_at is None:
            return False
        self._remaining = max(0.0, self._end_at - time.time())
        snap = self.snapshot()

        if not self._warned_5 and snap.remaining_sec <= 300 and snap.remaining_sec > 60:
            self._warned_5 = True
        if not self._warned_1 and snap.remaining_sec <= 60 and snap.remaining_sec > 0:
            self._warned_1 = True

        self._emit()
        if self._remaining <= 0:
            self._state = TimerState.FINISHED
            if self._on_finish:
                self._on_finish()
            return True
        return False

    @property
    def should_warn_5min(self) -> bool:
        return self._warned_5 and self.snapshot().remaining_sec <= 300

    def _emit(self) -> None:
        if self._on_tick:
            self._on_tick(self.snapshot())
