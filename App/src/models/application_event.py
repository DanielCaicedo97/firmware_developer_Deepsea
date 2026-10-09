"""Application events: the one contract between controllers and output adapters.

Controllers publish these events and every output mode (dashboard or grader)
consumes the same ones. The values are unformatted; rounding, hex formatting
and JSON field names are an output concern.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import ClassVar, Union

from protocol.diagnostic.models import DiagnosticResult
from protocol.fault.models import FaultResult
from protocol.telemetry.models import TelemetryResult


class EventType(Enum):
    """Event kinds; the values are ADAPTER.md's ``type`` field."""

    TELEMETRY = "telemetry"
    FAULT = "fault"
    DIAG_COMPLETE = "diag_complete"
    STATS = "stats"


@dataclass(frozen=True)
class TelemetryEvent:
    """A telemetry message was decoded."""

    event_type: ClassVar[EventType] = EventType.TELEMETRY
    telemetry: TelemetryResult


@dataclass(frozen=True)
class FaultEvent:
    """A fault message was decoded."""

    event_type: ClassVar[EventType] = EventType.FAULT
    fault: FaultResult


@dataclass(frozen=True)
class DiagnosticCompleteEvent:
    """An identification string was reassembled and decoded.

    ``completed_at_ns`` is the transport's ``time.monotonic_ns()`` at the
    moment reassembly completed, carried unchanged from the message metadata.
    """

    event_type: ClassVar[EventType] = EventType.DIAG_COMPLETE
    diagnostic: DiagnosticResult
    completed_at_ns: int


@dataclass(frozen=True)
class StatsEvent:
    """Processing statistics; ``frames_processed`` excludes noise frames."""

    event_type: ClassVar[EventType] = EventType.STATS
    frames_processed: int


ApplicationEvent = Union[TelemetryEvent, FaultEvent, DiagnosticCompleteEvent, StatsEvent]
