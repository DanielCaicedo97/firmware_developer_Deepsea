"""Grader mode: one ADAPTER.md NDJSON line per application event on stdout.

Only JSON lines go to the stream; diagnostics go to stderr through logging.
Field names and values follow ADAPTER.md (a flat object with a ``type``
field), which takes precedence over the illustrative ``event``/``data`` shape
in feature spec 06.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, TextIO

from models.application_event import (
    ApplicationEvent,
    DiagnosticCompleteEvent,
    EventType,
    FaultEvent,
    StatsEvent,
    TelemetryEvent,
)
from services.event_publisher import EventConsumer

# ADAPTER.md/code standards: volts and amps to 2 decimals, matching the generator log.
MEASUREMENT_DECIMALS = 2

JsonObject = Dict[str, Any]


def _telemetry_fields(event: TelemetryEvent) -> JsonObject:
    """ADAPTER.md ``telemetry`` fields."""
    telemetry = event.telemetry
    return {
        "module": telemetry.module_id,
        "seq": telemetry.sequence,
        "voltage": round(telemetry.voltage_v, MEASUREMENT_DECIMALS),
        "current": round(telemetry.current_a, MEASUREMENT_DECIMALS),
        "temp_c": int(telemetry.temperature_c),
        "enabled": telemetry.enabled,
        "fault": telemetry.fault,
        "derated": telemetry.derated,
    }


def _fault_fields(event: FaultEvent) -> JsonObject:
    """ADAPTER.md ``fault`` fields."""
    return {"module": event.fault.module_id, "code": int(event.fault.code)}


def _diag_complete_fields(event: DiagnosticCompleteEvent) -> JsonObject:
    """ADAPTER.md ``diag_complete`` fields; ``string`` is the exact received text."""
    return {
        "can_id": f"{event.diagnostic.message_id:#x}",
        "string": event.diagnostic.text,
        "ts_ns": event.completed_at_ns,
    }


def _stats_fields(event: StatsEvent) -> JsonObject:
    """ADAPTER.md ``stats`` fields."""
    return {"frames_processed": event.frames_processed}


_FIELD_BUILDERS: Dict[EventType, Callable[[Any], JsonObject]] = {
    EventType.TELEMETRY: _telemetry_fields,
    EventType.FAULT: _fault_fields,
    EventType.DIAG_COMPLETE: _diag_complete_fields,
    EventType.STATS: _stats_fields,
}


def to_json_object(event: ApplicationEvent) -> JsonObject:
    """Return the ADAPTER.md object for ``event``, ``type`` first."""
    fields: JsonObject = {"type": event.event_type.value}
    fields.update(_FIELD_BUILDERS[event.event_type](event))
    return fields


def to_json_line(event: ApplicationEvent) -> str:
    """Return ``event`` as one NDJSON line.

    ``allow_nan=False`` makes a NaN or infinity raise ``ValueError`` instead of
    producing a line that strict JSON parsers reject.
    """
    return json.dumps(to_json_object(event), allow_nan=False) + "\n"


class GraderOutput(EventConsumer):
    """Writes each event as one JSON line to ``stream`` and flushes it immediately.

    A line is fully serialized before anything is written, so a serialization
    error never leaves a partial line on the stream.
    """

    def __init__(self, stream: TextIO) -> None:
        self._stream = stream

    def on_event(self, event: ApplicationEvent) -> None:
        """Serialize ``event`` as one NDJSON line."""
        self._stream.write(to_json_line(event))
        self._stream.flush()
