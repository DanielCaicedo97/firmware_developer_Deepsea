"""Application controller: coordinates the overall processing flow."""

from __future__ import annotations

import logging
import time
from typing import Callable, Optional

from controllers.results import ControllerResult
from models.message import Message
from routes.common.results import DispatchResult
from services.event_publisher import EventPublisher
from services.stats_service import StatsService
from transport.listener import TransportListener
from transport.transport import FrameOutcome

logger = logging.getLogger(__name__)

Clock = Callable[[], int]
FramePoll = Callable[[], Optional[FrameOutcome]]
MessageDispatch = Callable[[Message], DispatchResult]


def _always() -> bool:
    """Default run condition: keep running until interrupted."""
    return True


class ApplicationController(TransportListener):
    """Connects complete messages to the routes and frame outcomes to statistics.

    As the transport's listener it dispatches every complete message through
    ``dispatch`` (the root router's ``dispatch``). It counts every frame the
    transport did not ignore, publishes stats periodically and once more at
    shutdown. It never sees raw frames, only their ``FrameOutcome``.
    """

    def __init__(
        self,
        dispatch: MessageDispatch,
        stats: StatsService,
        publisher: EventPublisher,
        clock: Clock = time.monotonic_ns,
    ) -> None:
        self._dispatch = dispatch
        self._stats = stats
        self._publisher = publisher
        self._clock = clock

    def on_message(self, message: Message) -> None:
        """Route one complete message; an unhandled or rejected message is logged and dropped."""
        dispatched = self._dispatch(message)
        if not dispatched.succeeded:
            logger.debug(
                "message %#x not handled (%s): %s", message.message_id, dispatched.status.value, dispatched.error
            )
        elif isinstance(dispatched.result, ControllerResult) and not dispatched.result.succeeded:
            logger.warning("message %#x rejected by controller: %s", message.message_id, dispatched.result.reason)

    def on_frame(self, outcome: Optional[FrameOutcome]) -> None:
        """Count one transport outcome; ``None`` (nothing received) and noise are not frames."""
        if outcome is not None and outcome is not FrameOutcome.IGNORED:
            self._stats.record_frame()

    def report_stats_if_due(self) -> None:
        """Publish a stats event when the reporting interval has elapsed."""
        event = self._stats.poll(self._clock())
        if event is not None:
            self._publisher.publish(event)

    def run(self, poll_frame: FramePoll, keep_running: Callable[[], bool] = _always) -> None:
        """Process frames from ``poll_frame`` until ``keep_running`` returns False.

        ``poll_frame`` receives and processes at most one frame, returning its
        outcome or ``None`` on a receive timeout, so stats keep flowing on an
        idle bus.
        """
        while keep_running():
            self.on_frame(poll_frame())
            self.report_stats_if_due()

    def shutdown(self) -> None:
        """Publish the final statistics."""
        self._publisher.publish(self._stats.stats_event())
