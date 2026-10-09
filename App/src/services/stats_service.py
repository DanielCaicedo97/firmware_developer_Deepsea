"""Processing statistics required by the challenge."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Dict, Mapping, Optional

from models.application_event import EventType, StatsEvent

# Domains whose controllers report processed and rejected results.
DOMAIN_EVENT_TYPES = (EventType.TELEMETRY, EventType.FAULT, EventType.DIAG_COMPLETE)


@dataclass(frozen=True)
class StatsSnapshot:
    """An immutable copy of every counter; the mappings are read-only copies."""

    frames_processed: int
    processed: Mapping[EventType, int]
    rejected: Mapping[EventType, int]


class StatsService:
    """Counts real frames and per-domain controller results, and schedules stats reports.

    Single counting point: ``record_frame`` is called only by
    ``ApplicationController.on_frame``, once per received frame whose transport
    outcome is not ``IGNORED``. The transport's framing map holds exactly the
    telemetry (0x100-0x103), fault (0x1F0) and diagnostic (0x6F0-0x6F3) IDs, so
    noise (0x200-0x2FF) is never counted, and every diagnostic frame counts
    once (even if its message is later abandoned), never per completed message.
    The per-domain counters are fed by the controllers. Only
    ``frames_processed`` goes into the ADAPTER.md stats event.
    """

    def __init__(self, report_interval_ns: int) -> None:
        if report_interval_ns <= 0:
            raise ValueError("stats report interval must be positive")
        self._report_interval_ns = report_interval_ns
        self._frames_processed = 0
        self._last_report_ns: Optional[int] = None
        self._processed: Dict[EventType, int] = dict.fromkeys(DOMAIN_EVENT_TYPES, 0)
        self._rejected: Dict[EventType, int] = dict.fromkeys(DOMAIN_EVENT_TYPES, 0)

    @property
    def frames_processed(self) -> int:
        """Running total of real frames processed."""
        return self._frames_processed

    def record_frame(self) -> None:
        """Count one received frame on a supported ID."""
        self._frames_processed += 1

    def record_processed(self, domain: EventType) -> None:
        """Count one decoded result a controller applied and published."""
        self._processed[self._domain(domain)] += 1

    def record_rejected(self, domain: EventType) -> None:
        """Count one decoded result a controller rejected."""
        self._rejected[self._domain(domain)] += 1

    def processed(self, domain: EventType) -> int:
        """Number of results the ``domain`` controller applied."""
        return self._processed[self._domain(domain)]

    def rejected(self, domain: EventType) -> int:
        """Number of results the ``domain`` controller rejected."""
        return self._rejected[self._domain(domain)]

    def snapshot(self) -> StatsSnapshot:
        """Return an immutable copy of every counter."""
        return StatsSnapshot(
            frames_processed=self._frames_processed,
            processed=MappingProxyType(dict(self._processed)),
            rejected=MappingProxyType(dict(self._rejected)),
        )

    def stats_event(self) -> StatsEvent:
        """Return the ADAPTER.md ``stats`` event for the current counters."""
        return StatsEvent(frames_processed=self._frames_processed)

    def poll(self, now_ns: int) -> Optional[StatsEvent]:
        """Return a stats event if a report is due at ``now_ns``, else ``None``.

        The first poll always reports; later ones report once
        ``report_interval_ns`` has elapsed since the previous report.
        """
        last_report_ns = self._last_report_ns
        if last_report_ns is not None and now_ns - last_report_ns < self._report_interval_ns:
            return None
        self._last_report_ns = now_ns
        return self.stats_event()

    @staticmethod
    def _domain(domain: EventType) -> EventType:
        """Validate that ``domain`` is a controller domain."""
        if domain not in DOMAIN_EVENT_TYPES:
            raise ValueError(f"not a controller domain: {domain}")
        return domain
