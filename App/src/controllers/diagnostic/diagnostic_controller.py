"""Diagnostic (identification string) controller."""

from __future__ import annotations

from typing import Optional

from controllers.base_controller import BaseController
from controllers.results import ControllerResult
from models.application_event import DiagnosticCompleteEvent, EventType
from models.message import Message
from protocol.diagnostic.models import DiagnosticResult


class DiagnosticController(BaseController[DiagnosticResult]):
    """Keeps each module's latest identification string and publishes each completion.

    The event's timestamp is the transport's ``completed_at_ns``, taken when
    reassembly completed; it is never re-read here. A message without it is
    incomplete and is rejected.
    """

    event_type = EventType.DIAG_COMPLETE

    def handle(self, result: DiagnosticResult, message: Message) -> ControllerResult:
        """Store a valid ``result`` and publish it with the message's completion timestamp."""
        completed_at_ns = message.metadata.completed_at_ns
        if completed_at_ns is None:
            return self._reject(result, f"message {message.message_id:#x} has no completion timestamp")
        reason = self._invalid_reason(result, message)
        if reason is not None:
            return self._reject(result, reason)
        self._state.update_identification(result, completed_at_ns)
        return self._complete(result, DiagnosticCompleteEvent(diagnostic=result, completed_at_ns=completed_at_ns))

    def _invalid_reason(self, result: DiagnosticResult, message: Message) -> Optional[str]:
        """Return why ``result`` must not update state, or ``None`` if it is valid."""
        if not self._module_known(result.module_id):
            return f"diagnostic module out of range: {result.module_id}"
        if result.message_id != message.message_id:
            return f"diagnostic result for {result.message_id:#x} arrived on {message.message_id:#x}"
        if not result.text:
            return "empty identification string"
        return None
