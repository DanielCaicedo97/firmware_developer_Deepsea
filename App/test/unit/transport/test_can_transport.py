"""Unit tests for CanTransport classification, outcomes and listener delivery."""

import unittest

from config.constants import DIAGNOSTIC_BASE_ID, FAULT_ID, MODULE_COUNT, TELEMETRY_BASE_ID
from config.settings import TransportConfig, build_framing_map
from helpers import FakeClock, RecordingListener, consecutive_frame, first_frame, interleave, segment_message
from models.can_frame import CANFrame
from models.message import FramingMode
from transport.can_transport import CanTransport
from transport.transport import FrameOutcome

MESSAGE = b"SN:PMU-4472-B FW:2.3.1 #7"


class FakeCommunication:
    """Communication double returning queued frames, then ``None`` (timeout)."""

    def __init__(self, frames: list) -> None:
        self.frames = list(frames)

    def receive(self) -> object:
        return self.frames.pop(0) if self.frames else None


class CompletionTimestampTest(unittest.TestCase):
    """The transport stamps ``completed_at_ns`` when a message completes."""

    def setUp(self) -> None:
        self.clock = FakeClock()
        self.transport = CanTransport(TransportConfig(framing=build_framing_map()), clock=self.clock)
        self.listener = RecordingListener()
        self.transport.add_listener(self.listener)

    def test_segmented_message_stamped_when_reassembly_completes(self) -> None:
        frames = segment_message(DIAGNOSTIC_BASE_ID, MESSAGE)
        for index, frame in enumerate(frames):
            self.clock.now = 1_000 + index
            self.transport.process(frame)
        message, = self.listener.messages
        self.assertEqual(message.metadata.completed_at_ns, 1_000 + len(frames) - 1)

    def test_single_frame_message_stamped_on_delivery(self) -> None:
        self.clock.now = 77
        self.transport.process(CANFrame(can_id=FAULT_ID, data=bytes(8), timestamp_ns=5))
        metadata = self.listener.messages[0].metadata
        self.assertEqual((metadata.received_at_ns, metadata.completed_at_ns), (5, 77))


class ReceiveFromTest(unittest.TestCase):
    """``receive_from`` consumes one unit from the communication interface."""

    def setUp(self) -> None:
        self.transport = CanTransport(TransportConfig(framing=build_framing_map()))

    def test_returns_the_outcome_of_the_received_frame(self) -> None:
        communication = FakeCommunication([CANFrame(can_id=FAULT_ID, data=bytes(8)), CANFrame(can_id=0x2A0, data=b"")])
        self.assertIs(self.transport.receive_from(communication), FrameOutcome.COMPLETED)
        self.assertIs(self.transport.receive_from(communication), FrameOutcome.IGNORED)

    def test_returns_none_when_nothing_arrived(self) -> None:
        self.assertIsNone(self.transport.receive_from(FakeCommunication([])))


class CanTransportTest(unittest.TestCase):
    """Behaviour of the CAN transport against the challenge framing map."""

    def setUp(self) -> None:
        self.transport = CanTransport(TransportConfig(framing=build_framing_map()))
        self.listener = RecordingListener()
        self.transport.add_listener(self.listener)

    def test_noise_range_is_ignored(self) -> None:
        for can_id in (0x200, 0x2A5, 0x2FF):
            self.assertIs(self.transport.process(CANFrame(can_id=can_id, data=bytes(8))), FrameOutcome.IGNORED)
        self.assertEqual(self.listener.messages, [])

    def test_single_frame_sources_complete_immediately(self) -> None:
        sources = [TELEMETRY_BASE_ID + module for module in range(MODULE_COUNT)] + [FAULT_ID]
        for can_id in sources:
            frame = CANFrame(can_id=can_id, data=bytes(range(8)), timestamp_ns=123)
            self.assertIs(self.transport.process(frame), FrameOutcome.COMPLETED)
        self.assertEqual([m.message_id for m in self.listener.messages], sources)
        message = self.listener.messages[0]
        self.assertEqual(message.payload, bytes(range(8)))
        self.assertIs(message.metadata.framing, FramingMode.SINGLE_FRAME)
        self.assertEqual(message.metadata.frame_count, 1)
        self.assertEqual(message.metadata.received_at_ns, 123)

    def test_segmented_message_delivered_only_on_completion(self) -> None:
        frames = segment_message(DIAGNOSTIC_BASE_ID, MESSAGE)
        outcomes = [self.transport.process(frame) for frame in frames]
        self.assertEqual(outcomes[:-1], [FrameOutcome.ACCEPTED] * (len(frames) - 1))
        self.assertIs(outcomes[-1], FrameOutcome.COMPLETED)
        self.assertEqual(len(self.listener.messages), 1)
        message = self.listener.messages[0]
        self.assertEqual(message.message_id, DIAGNOSTIC_BASE_ID)
        self.assertEqual(message.source_id, DIAGNOSTIC_BASE_ID)
        self.assertEqual(message.payload, MESSAGE)
        self.assertIs(message.metadata.framing, FramingMode.SEGMENTED)
        self.assertEqual(message.metadata.frame_count, len(frames))

    def test_interleaved_diagnostics_with_telemetry_and_noise(self) -> None:
        texts = {DIAGNOSTIC_BASE_ID + m: f"SN:PMU-447{m} FW:2.3.{m}".encode() for m in range(MODULE_COUNT)}
        frames = interleave(*(segment_message(can_id, text) for can_id, text in texts.items()))
        mixed = []
        for frame in frames:
            mixed += [frame, CANFrame(can_id=0x250, data=bytes(8)), CANFrame(can_id=TELEMETRY_BASE_ID, data=bytes(8))]
        for frame in mixed:
            self.transport.process(frame)
        diagnostics = {m.message_id: m.payload for m in self.listener.messages if m.message_id in texts}
        self.assertEqual(diagnostics, texts)
        self.assertEqual(sum(m.message_id == TELEMETRY_BASE_ID for m in self.listener.messages), len(frames))

    def test_malformed_sequences_are_rejected_and_not_delivered(self) -> None:
        can_id = DIAGNOSTIC_BASE_ID + 2
        rejected = [
            consecutive_frame(can_id, 5, bytes(7)),
            first_frame(can_id, 200, bytes(6)),
        ]
        for frame in rejected:
            self.assertIs(self.transport.process(frame), FrameOutcome.REJECTED)
        broken = segment_message(can_id, MESSAGE)
        self.transport.process(broken[0])
        self.assertIs(self.transport.process(broken[2]), FrameOutcome.REJECTED)
        self.assertEqual(self.listener.messages, [])

    def test_multiple_listeners_and_duplicate_registration(self) -> None:
        second = RecordingListener()
        self.transport.add_listener(second)
        self.transport.add_listener(second)
        self.transport.process(CANFrame(can_id=FAULT_ID, data=bytes(8)))
        self.assertEqual(len(self.listener.messages), 1)
        self.assertEqual(len(second.messages), 1)

    def test_removed_listener_is_not_notified(self) -> None:
        self.transport.remove_listener(self.listener)
        self.transport.process(CANFrame(can_id=FAULT_ID, data=bytes(8)))
        self.assertEqual(self.listener.messages, [])

    def test_one_context_per_segmented_source(self) -> None:
        expected = {DIAGNOSTIC_BASE_ID + m for m in range(MODULE_COUNT)}
        self.assertEqual(set(self.transport.reassembler.contexts), expected)

    def test_framing_map_is_configurable(self) -> None:
        transport = CanTransport(TransportConfig(framing={0x6F0: FramingMode.SEGMENTED}))
        self.assertIs(transport.process(CANFrame(can_id=0x6F1, data=bytes(8))), FrameOutcome.IGNORED)
        self.assertEqual(set(transport.reassembler.contexts), {0x6F0})


if __name__ == "__main__":
    unittest.main()
