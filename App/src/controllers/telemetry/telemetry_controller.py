"""Telemetry controller."""

from __future__ import annotations

from typing import Optional

from config.constants import TELEMETRY_BASE_ID
from controllers.base_controller import BaseController
from controllers.results import ControllerResult
from models.application_event import EventType, TelemetryEvent
from models.message import Message
from protocol.telemetry.models import TelemetryResult


class TelemetryController(BaseController[TelemetryResult]):
    """Keeps each module's latest telemetry and publishes every valid reading."""

    event_type = EventType.TELEMETRY

    def handle(self, result: TelemetryResult, message: Message) -> ControllerResult:
        """Store a valid ``result`` as the module's latest telemetry and publish it."""
        reason = self._invalid_reason(result, message)
        if reason is not None:
            return self._reject(result, reason)
        self._state.update_telemetry(result)
        return self._complete(result, TelemetryEvent(telemetry=result))

    def _invalid_reason(self, result: TelemetryResult, message: Message) -> Optional[str]:
        """Return why ``result`` must not update state, or ``None`` if it is valid."""
        if not self._module_known(result.module_id):
            return f"telemetry module out of range: {result.module_id}"
        if message.message_id != TELEMETRY_BASE_ID + result.module_id:
            return f"telemetry for module {result.module_id} arrived on {message.message_id:#x}"
        return None
