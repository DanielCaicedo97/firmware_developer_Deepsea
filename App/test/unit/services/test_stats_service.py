"""Unit tests for StatsService and its single frame-counting point."""

import dataclasses
import unittest
from typing import List

from config.constants import (
    DIAGNOSTIC_BASE_ID,
    FAULT_ID,
    MODULE_COUNT,
    NOISE_ID_FIRST,
    NOISE_ID_LAST,
    TELEMETRY_BASE_ID,
)
from config.settings import TransportConfig, build_framing_map
from controllers.application_controller import ApplicationController
from controllers.diagnostic import DiagnosticController
from controllers.fault import FaultController
from controllers.telemetry import TelemetryController
from helpers import RecordingPublisher, first_frame, segment_message
from models.application_event import EventType, StatsEvent
from models.can_frame import CANFrame
from routes.routes_init import init_routes
from services.application_state import ApplicationState
from services.stats_service import StatsService, StatsSnapshot
from transport.can_transport import CanTransport

INTERVAL_NS = 1_000
TELEMETRY_PAYLOAD = bytes([0x1B, 0x10, 0x4F, 0x2E, 0x57, 0x05, 0xD5, 0x12])
FAULT_PAYLOAD = bytes([2, 1, 0, 0, 0, 0, 0, 0])


class StatsServiceTest(unittest.TestCase):
    """Frame counting, snapshots and the periodic report schedule."""

    def setUp(self) -> None:
        self.stats = StatsService(INTERVAL_NS)

    def test_counts_recorded_frames(self) -> None:
        for _ in range(5):
            self.stats.record_frame()
        self.assertEqual(self.stats.frames_processed, 5)
        self.assertEqual(self.stats.snapshot().frames_processed, 5)
        self.assertEqual(self.stats.stats_event(), StatsEvent(frames_processed=5))

    def test_first_poll_reports_immediately(self) -> None:
        self.assertEqual(self.stats.poll(50), StatsEvent(frames_processed=0))

    def test_reports_again_only_after_the_interval(self) -> None:
        self.stats.poll(0)
        self.stats.record_frame()
        self.assertIsNone(self.stats.poll(INTERVAL_NS - 1))
        self.assertEqual(self.stats.poll(INTERVAL_NS), StatsEvent(frames_processed=1))
        self.assertIsNone(self.stats.poll(INTERVAL_NS + 1))

    def test_counts_processed_and_rejected_results_per_domain(self) -> None:
        self.stats.record_processed(EventType.TELEMETRY)
        self.stats.record_processed(EventType.TELEMETRY)
        self.stats.record_rejected(EventType.FAULT)
        self.stats.record_processed(EventType.DIAG_COMPLETE)
        counts = [(self.stats.processed(t), self.stats.rejected(t))
                  for t in (EventType.TELEMETRY, EventType.FAULT, EventType.DIAG_COMPLETE)]
        self.assertEqual(counts, [(2, 0), (0, 1), (1, 0)])
        self.assertEqual(self.stats.stats_event(), StatsEvent(frames_processed=0))

    def test_snapshot_holds_every_counter(self) -> None:
        self.stats.record_frame()
        self.stats.record_processed(EventType.FAULT)
        self.stats.record_rejected(EventType.DIAG_COMPLETE)
        self.assertEqual(
            self.stats.snapshot(),
            StatsSnapshot(
                frames_processed=1,
                processed={EventType.TELEMETRY: 0, EventType.FAULT: 1, EventType.DIAG_COMPLETE: 0},
                rejected={EventType.TELEMETRY: 0, EventType.FAULT: 0, EventType.DIAG_COMPLETE: 1},
            ),
        )

    def test_snapshot_is_immutable_and_detached(self) -> None:
        snapshot = self.stats.snapshot()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            snapshot.frames_processed = 10  # type: ignore[misc]
        with self.assertRaises(TypeError):
            snapshot.processed[EventType.FAULT] = 10  # type: ignore[index]
        self.stats.record_frame()
        self.stats.record_processed(EventType.FAULT)
        self.assertEqual(snapshot.frames_processed, 0)
        self.assertEqual(snapshot.processed[EventType.FAULT], 0)
        self.assertEqual(self.stats.processed(EventType.FAULT), 1)

    def test_snapshots_are_deterministic(self) -> None:
        other = StatsService(INTERVAL_NS)
        for stats in (self.stats, other):
            stats.record_frame()
            stats.record_processed(EventType.TELEMETRY)
        self.assertEqual(self.stats.snapshot(), other.snapshot())
        self.assertEqual(self.stats.snapshot(), self.stats.snapshot())

    def test_rejects_a_non_domain_counter(self) -> None:
        with self.assertRaises(ValueError):
            self.stats.record_processed(EventType.STATS)

    def test_rejects_a_non_positive_interval(self) -> None:
        with self.assertRaises(ValueError):
            StatsService(0)


class FrameCountingPointTest(unittest.TestCase):
    """``frames_processed`` through the real transport, router and controllers.

    ``ApplicationController.on_frame`` is the only caller of ``record_frame``;
    these tests show that each relevant frame is counted exactly once however
    many layers it passes through, and that noise never is.
    """

    def setUp(self) -> None:
        self.stats = StatsService(INTERVAL_NS)
        state = ApplicationState()
        publisher = RecordingPublisher()
        self.events = publisher.events
        root = init_routes(
            TelemetryController(state, self.stats, publisher),
            FaultController(state, self.stats, publisher),
            DiagnosticController(state, self.stats, publisher),
        )
        self.transport = CanTransport(TransportConfig(framing=build_framing_map()))
        self.application = ApplicationController(root.dispatch, self.stats, publisher)
        self.transport.add_listener(self.application)

    def feed(self, frames: List[CANFrame]) -> None:
        for frame in frames:
            self.application.on_frame(self.transport.process(frame))

    def test_every_relevant_identifier_is_counted(self) -> None:
        telemetry = [CANFrame(TELEMETRY_BASE_ID + m, TELEMETRY_PAYLOAD) for m in range(MODULE_COUNT)]
        diagnostics = [first_frame(DIAGNOSTIC_BASE_ID + m, 20, b"SN:PMU") for m in range(MODULE_COUNT)]
        self.feed(telemetry + [CANFrame(FAULT_ID, FAULT_PAYLOAD)] + diagnostics)
        self.assertEqual(self.stats.frames_processed, 2 * MODULE_COUNT + 1)

    def test_noise_identifiers_are_never_counted(self) -> None:
        self.feed([CANFrame(can_id, bytes(8)) for can_id in range(NOISE_ID_FIRST, NOISE_ID_LAST + 1)])
        self.assertEqual(self.stats.frames_processed, 0)
        self.assertEqual(self.events, [])

    def test_a_segmented_message_counts_each_frame_once_not_per_layer(self) -> None:
        frames = segment_message(DIAGNOSTIC_BASE_ID, b"SN:PMU-4471-A FW:2.3.1")
        self.feed(frames)
        self.assertEqual(self.stats.frames_processed, len(frames))
        self.assertEqual(self.stats.processed(EventType.DIAG_COMPLETE), 1)
        self.assertEqual([event.event_type for event in self.events], [EventType.DIAG_COMPLETE])

    def test_single_frames_count_once_when_decoded_and_published(self) -> None:
        self.feed([CANFrame(TELEMETRY_BASE_ID, TELEMETRY_PAYLOAD), CANFrame(FAULT_ID, FAULT_PAYLOAD)])
        self.assertEqual(self.stats.frames_processed, 2)
        self.assertEqual(len(self.events), 2)

    def test_abandoned_and_malformed_frames_on_real_ids_still_count(self) -> None:
        self.feed([first_frame(DIAGNOSTIC_BASE_ID, 200, bytes(6)), CANFrame(FAULT_ID, bytes(3))])
        self.assertEqual(self.stats.frames_processed, 2)
        self.assertEqual(self.events, [])


if __name__ == "__main__":
    unittest.main()
