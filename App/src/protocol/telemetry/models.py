"""Decoded power module telemetry."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TelemetryResult:
    """One decoded telemetry message from a power module.

    ``module_id`` comes from the telemetry CAN ID; ``sequence`` is the
    payload's per-send counter. Values are in volts, amps and degrees Celsius,
    unrounded; presentation layers decide how to format them.
    """

    module_id: int
    sequence: int
    voltage_v: float
    current_a: float
    temperature_c: int
    enabled: bool
    fault: bool
    derated: bool
