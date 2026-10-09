"""Unit tests for ApplicationController."""

import unittest
from typing import Iterator, List, Optional

from config.constants import FAULT_ID
from controllers.application_controller import ApplicationController
from controllers.results import ControllerResult, ControllerStatus
from helpers import FakeClock, RecordingPublisher, complete_message
from models.application_event import StatsEvent
from models.message import Message
from routes.common import DispatchResult, DispatchStatus
from services.stats_service import StatsService
from transport.listener import TransportListener
from transport.transport import FrameOutcome

INTERVAL_NS = 1_000


class RecordingDispatch:
    """Dispatch double returning a fixed status."""

    def __init__(self, status: DispatchStatus = DispatchStatus.SUCCESS) -> None:
        self.status = status
        self.messages: List[Message] = []

    def __call__(self, message: Message) -> DispatchResult:
        self.messages.append(message)
        return DispatchResult(self.status, message)


class ApplicationControllerTest(unittest.TestCase):
    """Message dispatch, frame accounting, periodic and final stats."""

    def setUp(self) -> None:
        self.dispatch = RecordingDispatch()
        self.publisher = RecordingPublisher()
        self.clock = FakeClock()
        self.controller = ApplicationController(self.dispatch, StatsService(INTERVAL_NS), self.publisher, self.clock)

    def test_is_a_transport_listener_that_dispatches_messages(self) -> None:
        self.assertIsInstance(self.controller, TransportListener)
        message = complete_message(FAULT_ID, bytes(8))
        self.controller.on_message(message)
        self.assertEqual(self.dispatch.messages, [message])

    def test_failed_dispatch_does_not_raise(self) -> None:
        self.dispatch.status = DispatchStatus.HANDLER_FAILED
        self.controller.on_message(complete_message(FAULT_ID, bytes(2)))
        self.assertEqual(self.publisher.events, [])

    def test_controller_rejection_is_logged_not_raised(self) -> None:
        message = complete_message(FAULT_ID, bytes(8))
        rejected = ControllerResult(ControllerStatus.REJECTED, None, reason="unknown fault code")
        controller = ApplicationController(lambda m: DispatchResult(DispatchStatus.SUCCESS, m, "fault", rejected),
                                           StatsService(INTERVAL_NS), self.publisher, self.clock)
        with self.assertLogs("controllers.application_controller", "WARNING") as logs:
            controller.on_message(message)
        self.assertIn("unknown fault code", logs.output[0])
        self.assertEqual(self.publisher.events, [])

    def test_counts_every_frame_except_noise_and_timeouts(self) -> None:
        outcomes: List[Optional[FrameOutcome]] = [
            FrameOutcome.COMPLETED, FrameOutcome.ACCEPTED, FrameOutcome.REJECTED,
            FrameOutcome.IGNORED, None, FrameOutcome.IGNORED,
        ]
        for outcome in outcomes:
            self.controller.on_frame(outcome)
        self.controller.shutdown()
        self.assertEqual(self.publisher.events, [StatsEvent(frames_processed=3)])

    def test_reports_stats_periodically(self) -> None:
        self.controller.report_stats_if_due()
        self.controller.on_frame(FrameOutcome.COMPLETED)
        self.clock.now = INTERVAL_NS - 1
        self.controller.report_stats_if_due()
        self.clock.now = INTERVAL_NS
        self.controller.report_stats_if_due()
        self.assertEqual(self.publisher.events, [StatsEvent(0), StatsEvent(1)])

    def test_run_polls_until_stopped_and_reports_on_idle_bus(self) -> None:
        polls: Iterator[Optional[FrameOutcome]] = iter([FrameOutcome.COMPLETED, None, FrameOutcome.IGNORED])
        remaining = [3]

        def keep_running() -> bool:
            remaining[0] -= 1
            return remaining[0] >= 0

        self.controller.run(lambda: next(polls), keep_running)
        self.controller.shutdown()
        self.assertEqual(self.publisher.events, [StatsEvent(1), StatsEvent(1)])


if __name__ == "__main__":
    unittest.main()
