"""Normal mode: an in-place terminal dashboard drawn with plain ANSI sequences.

No curses or UI library: the cursor goes home, every line is redrawn and
cleared to its end, and anything left below is cleared.
"""

from __future__ import annotations

import time
from typing import Callable, List, Optional, TextIO

from config.constants import DIAGNOSTIC_BASE_ID
from models.application_event import ApplicationEvent, EventType
from protocol.fault.models import FaultResult
from protocol.telemetry.models import TelemetryResult
from services.application_state import ApplicationState, StateSnapshot
from services.event_publisher import EventConsumer

CURSOR_HOME = "\x1b[H"
CLEAR_TO_LINE_END = "\x1b[K"
CLEAR_TO_SCREEN_END = "\x1b[J"

TITLE = "DeepSea CAN Diagnostic Tool"
SEPARATOR = "-" * 60

Clock = Callable[[], int]


def format_telemetry_line(module_id: int, telemetry: Optional[TelemetryResult]) -> str:
    """One module's latest readings, or a placeholder before the first one."""
    if telemetry is None:
        return f"Module {module_id}:  (no telemetry yet)"
    return (
        f"Module {module_id}: {telemetry.voltage_v:6.1f}V {telemetry.current_a:7.2f}A {telemetry.temperature_c:4d}C"
        f"   enabled={telemetry.enabled}  fault={telemetry.fault}  derated={telemetry.derated}"
        f"  seq={telemetry.sequence}"
    )


def format_fault_line(fault: FaultResult) -> str:
    """One recent fault."""
    return f"  module {fault.module_id}, code {int(fault.code)} ({fault.code.name.lower()})"


def format_dashboard(snapshot: StateSnapshot, frames_processed: int) -> List[str]:
    """Return the dashboard's lines for one state snapshot."""
    lines = [TITLE, SEPARATOR]
    lines += [format_telemetry_line(m, telemetry) for m, telemetry in enumerate(snapshot.telemetry)]
    lines += [SEPARATOR, "Identification strings:"]
    for module_id, completion in enumerate(snapshot.diagnostic_completions):
        text = completion.diagnostic.text if completion is not None else "(not yet received)"
        lines.append(f"  {DIAGNOSTIC_BASE_ID + module_id:#x}: {text}")
    lines += [SEPARATOR, "Recent faults:"]
    lines += [format_fault_line(fault) for fault in snapshot.recent_faults] or ["  (none)"]
    lines += [SEPARATOR, f"Frames processed: {frames_processed}"]
    return lines


class Dashboard(EventConsumer):
    """Redraws the dashboard from an ``ApplicationState`` snapshot as events arrive.

    Events only trigger redraws; the values shown come from the state, which
    controllers already updated, so nothing is decoded here. Stats events
    always redraw (they arrive periodically and once more at shutdown, so the
    last frame drawn is the final state); other events redraw at most once per
    ``refresh_interval_ns`` so a busy bus does not flood the terminal.
    """

    def __init__(
        self,
        state: ApplicationState,
        stream: TextIO,
        refresh_interval_ns: int,
        clock: Clock = time.monotonic_ns,
    ) -> None:
        self._state = state
        self._stream = stream
        self._refresh_interval_ns = refresh_interval_ns
        self._clock = clock
        self._frames_processed = 0
        self._last_render_ns: Optional[int] = None

    def on_event(self, event: ApplicationEvent) -> None:
        """Take note of ``event`` and redraw when due."""
        now_ns = self._clock()
        if event.event_type is EventType.STATS:
            self._frames_processed = event.frames_processed
            self.render(now_ns)
        elif self._render_due(now_ns):
            self.render(now_ns)

    def render(self, now_ns: int) -> None:
        """Redraw the whole dashboard in place."""
        lines = format_dashboard(self._state.snapshot(), self._frames_processed)
        body = "".join(line + CLEAR_TO_LINE_END + "\n" for line in lines)
        self._stream.write(CURSOR_HOME + body + CLEAR_TO_SCREEN_END)
        self._stream.flush()
        self._last_render_ns = now_ns

    def _render_due(self, now_ns: int) -> bool:
        """True if no redraw happened within the refresh interval."""
        return self._last_render_ns is None or now_ns - self._last_render_ns >= self._refresh_interval_ns
