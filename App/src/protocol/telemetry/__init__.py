"""Telemetry domain: decodes power module telemetry into ``TelemetryResult``."""

from protocol.telemetry.decoder import decode_telemetry
from protocol.telemetry.models import TelemetryResult

__all__ = ["TelemetryResult", "decode_telemetry"]
