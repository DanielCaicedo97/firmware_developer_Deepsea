"""Latest application-level state of the power modules."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, List, Optional, Tuple

from config.constants import DEFAULT_RECENT_FAULT_LIMIT, DIAGNOSTIC_BASE_ID, MODULE_COUNT
from models.application_event import DiagnosticCompleteEvent
from protocol.diagnostic.models import DiagnosticResult
from protocol.fault.models import FaultCode, FaultResult
from protocol.telemetry.models import TelemetryResult


@dataclass(frozen=True)
class StateSnapshot:
    """An immutable copy of the application state; tuples are indexed by module."""

    telemetry: Tuple[Optional[TelemetryResult], ...]
    latest_faults: Tuple[Optional[FaultResult], ...]
    diagnostic_completions: Tuple[Optional[DiagnosticCompleteEvent], ...]
    recent_faults: Tuple[FaultResult, ...]

    @property
    def module_count(self) -> int:
        """Number of power modules in the snapshot."""
        return len(self.telemetry)


class ApplicationState:
    """Owns the latest telemetry, fault and diagnostic completion per module, and the recent faults.

    Storage is fixed at construction: one slot of each kind per module, and at
    most ``recent_fault_limit`` faults (oldest dropped first). Nothing grows
    with the amount of traffic. Every update is validated before it is
    committed, so an invalid one raises ``ValueError``/``TypeError`` and leaves
    the last valid state in place. Results are frozen and accessors return
    them or tuples, so no internal collection is exposed.
    """

    def __init__(self, module_count: int = MODULE_COUNT, recent_fault_limit: int = DEFAULT_RECENT_FAULT_LIMIT) -> None:
        if module_count <= 0:
            raise ValueError("module count must be positive")
        if recent_fault_limit <= 0:
            raise ValueError("recent fault limit must be positive")
        self._telemetry: List[Optional[TelemetryResult]] = [None] * module_count
        self._latest_faults: List[Optional[FaultResult]] = [None] * module_count
        self._completions: List[Optional[DiagnosticCompleteEvent]] = [None] * module_count
        self._recent_faults: Deque[FaultResult] = deque(maxlen=recent_fault_limit)

    @property
    def module_count(self) -> int:
        """Number of power modules tracked."""
        return len(self._telemetry)

    @property
    def recent_faults(self) -> Tuple[FaultResult, ...]:
        """The most recent faults, oldest first."""
        return tuple(self._recent_faults)

    def update_telemetry(self, telemetry: TelemetryResult) -> None:
        """Replace the module's latest telemetry."""
        _require_type(telemetry, TelemetryResult)
        self._telemetry[self._module_index(telemetry.module_id)] = telemetry

    def telemetry(self, module_id: int) -> Optional[TelemetryResult]:
        """Return the module's latest telemetry, or ``None`` if none yet."""
        return self._telemetry[self._module_index(module_id)]

    def record_fault(self, fault: FaultResult) -> None:
        """Make ``fault`` the module's current fault and append it to the recent-fault history."""
        _require_type(fault, FaultResult)
        index = self._module_index(fault.module_id)
        if not isinstance(fault.code, FaultCode):
            raise ValueError(f"unknown fault code: {fault.code!r}")
        self._latest_faults[index] = fault
        self._recent_faults.append(fault)

    def latest_fault(self, module_id: int) -> Optional[FaultResult]:
        """Return the module's most recent fault, or ``None`` if none yet."""
        return self._latest_faults[self._module_index(module_id)]

    def update_identification(self, identification: DiagnosticResult, completed_at_ns: int) -> None:
        """Replace the module's latest identification string and its reassembly completion time."""
        _require_type(identification, DiagnosticResult)
        index = self._module_index(identification.module_id)
        if identification.message_id != DIAGNOSTIC_BASE_ID + index:
            raise ValueError(f"identification for module {index} has id {identification.message_id:#x}")
        if not identification.text:
            raise ValueError("empty identification string")
        if isinstance(completed_at_ns, bool) or not isinstance(completed_at_ns, int) or completed_at_ns < 0:
            raise ValueError(f"invalid completion timestamp: {completed_at_ns!r}")
        self._completions[index] = DiagnosticCompleteEvent(diagnostic=identification, completed_at_ns=completed_at_ns)

    def identification(self, module_id: int) -> Optional[DiagnosticResult]:
        """Return the module's latest identification string, or ``None`` if none yet."""
        completion = self.diagnostic_completion(module_id)
        return completion.diagnostic if completion is not None else None

    def diagnostic_completion(self, module_id: int) -> Optional[DiagnosticCompleteEvent]:
        """Return the module's latest diagnostic completion with its ``ts_ns``, or ``None``."""
        return self._completions[self._module_index(module_id)]

    def snapshot(self) -> StateSnapshot:
        """Return an immutable copy of the whole state."""
        return StateSnapshot(
            telemetry=tuple(self._telemetry),
            latest_faults=tuple(self._latest_faults),
            diagnostic_completions=tuple(self._completions),
            recent_faults=tuple(self._recent_faults),
        )

    def _module_index(self, module_id: int) -> int:
        """Validate ``module_id`` and return it as a slot index."""
        if isinstance(module_id, bool) or not isinstance(module_id, int):
            raise TypeError(f"module id must be an int: {module_id!r}")
        if not 0 <= module_id < self.module_count:
            raise ValueError(f"module id out of range: {module_id}")
        return module_id


def _require_type(value: object, expected: type) -> None:
    """Reject an update that is not the expected protocol result."""
    if not isinstance(value, expected):
        raise TypeError(f"expected {expected.__name__}, got {type(value).__name__}")
