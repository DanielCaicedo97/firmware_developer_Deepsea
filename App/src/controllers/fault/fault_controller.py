"""Fault controller."""

from __future__ import annotations

from typing import Optional

from controllers.base_controller import BaseController
from controllers.results import ControllerResult
from models.application_event import EventType, FaultEvent
from models.message import Message
from protocol.fault.models import FaultCode, FaultResult


class FaultController(BaseController[FaultResult]):
    """Records every valid fault in the recent-fault history and publishes it."""

    event_type = EventType.FAULT

    def handle(self, result: FaultResult, message: Message) -> ControllerResult:
        """Record a valid ``result`` and publish it."""
        reason = self._invalid_reason(result)
        if reason is not None:
            return self._reject(result, reason)
        self._state.record_fault(result)
        return self._complete(result, FaultEvent(fault=result))

    def _invalid_reason(self, result: FaultResult) -> Optional[str]:
        """Return why ``result`` must not update state, or ``None`` if it is valid."""
        if not self._module_known(result.module_id):
            return f"fault module out of range: {result.module_id}"
        if not isinstance(result.code, FaultCode):
            return f"unknown fault code: {result.code!r}"
        return None
