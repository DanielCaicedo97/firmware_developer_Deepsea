"""Contract shared by the per-domain controllers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar, Generic, TypeVar

from controllers.results import ControllerResult, ControllerStatus
from models.application_event import ApplicationEvent, EventType
from models.message import Message
from services.application_state import ApplicationState
from services.event_publisher import EventPublisher
from services.stats_service import StatsService

ResultT = TypeVar("ResultT")


class BaseController(ABC, Generic[ResultT]):
    """Applies application behavior to one domain's decoded results.

    Contract: ``handle`` is called once per successfully decoded message, with
    the decoder's result and the complete message it came from. It validates
    the result first. A valid result updates ``state``, publishes the domain's
    event and is counted as processed. An invalid one is counted as rejected
    and changes nothing else. Either way, ``handle`` returns a
    ``ControllerResult``. Service failures are not expected input, so they
    propagate to the caller.

    ``event_type`` names the domain in the statistics.
    """

    event_type: ClassVar[EventType]

    def __init__(self, state: ApplicationState, stats: StatsService, publisher: EventPublisher) -> None:
        self._state = state
        self._stats = stats
        self._publisher = publisher

    @abstractmethod
    def handle(self, result: ResultT, message: Message) -> ControllerResult:
        """Validate and apply one decoded ``result`` of ``message``."""

    def _module_known(self, module_id: int) -> bool:
        """True when ``module_id`` has a slot in the application state."""
        return 0 <= module_id < self._state.module_count

    def _reject(self, result: ResultT, reason: str) -> ControllerResult:
        """Count a rejected result; state and output are left untouched."""
        self._stats.record_rejected(self.event_type)
        return ControllerResult(ControllerStatus.REJECTED, result, reason=reason)

    def _complete(self, result: ResultT, event: ApplicationEvent) -> ControllerResult:
        """Publish ``event`` for an applied result and count it as processed."""
        self._publisher.publish(event)
        self._stats.record_processed(self.event_type)
        return ControllerResult(ControllerStatus.PROCESSED, result, event=event)
