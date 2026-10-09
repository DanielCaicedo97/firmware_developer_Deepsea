"""Integration: raw socket bytes -> SocketCanInterface -> CanTransport -> listener.

Uses the real communication and transport components composed from the
application config; only the kernel socket is replaced by a fake.
"""

import unittest
from collections import defaultdict
from typing import Dict, List

from communication.socketcan import SocketCanInterface
from config.constants import CAN_EXTENDED_FRAME_FLAG, DIAGNOSTIC_BASE_ID, FAULT_ID, MODULE_COUNT, TELEMETRY_BASE_ID
from config.settings import build_application_config
from helpers import (
    FakeCanSocket,
    RecordingListener,
    consecutive_frame,
    first_frame,
    interleave,
    raw_can_frame,
    segment_message,
    to_raw,
)
from models.can_frame import CANFrame
from transport.can_transport import CanTransport
from transport.transport import FrameOutcome

DIAGNOSTIC_IDS = [DIAGNOSTIC_BASE_ID + module for module in range(MODULE_COUNT)]


def recovery_text(module: int) -> bytes:
    """The clean message each module sends after its messy situation."""
    return f"SN:PMU-447{module + 1}-{'ABCD'[module]} FW:2.3.1 #{module}".encode("ascii")


def messy_openings() -> List[List[CANFrame]]:
    """One CHALLENGE.md situation per module, in module order."""
    orphan = [consecutive_frame(DIAGNOSTIC_IDS[0], 5, bytes(7))]
    restart = segment_message(DIAGNOSTIC_IDS[1], b"XX:DECOY-NOT-REAL-MSG")[:2]
    oversized = [first_frame(DIAGNOSTIC_IDS[2], 200, bytes(6))]
    broken = segment_message(DIAGNOSTIC_IDS[3], b"SN:PMU-4474-D FW:2.4.0 #0-BROKEN")
    out_of_order = [broken[0], broken[1], consecutive_frame(DIAGNOSTIC_IDS[3], 3, broken[3].data[1:])]
    return [orphan, restart, oversized, out_of_order]


def bus_traffic() -> List[bytes]:
    """Raw bus stream: messy openings, then interleaved recoveries mixed with
    telemetry, fault, noise and one invalid (extended) frame."""
    frames = interleave(*messy_openings())
    frames += interleave(*(segment_message(can_id, recovery_text(m)) for m, can_id in enumerate(DIAGNOSTIC_IDS)))
    raw: List[bytes] = []
    for index, frame in enumerate(frames):
        raw.append(to_raw(frame))
        raw.append(raw_can_frame(0x200 + index, bytes(8)))
        raw.append(raw_can_frame(TELEMETRY_BASE_ID + index % MODULE_COUNT, bytes(range(8))))
    raw.append(raw_can_frame(FAULT_ID, bytes([2, 1, 0, 0, 0, 0, 0, 0])))
    raw.append(raw_can_frame(0x6F0 | CAN_EXTENDED_FRAME_FLAG, bytes(8)))
    return raw


class SocketCanToTransportTest(unittest.TestCase):
    """The communication layer feeding the transport layer end to end, offline."""

    def setUp(self) -> None:
        config = build_application_config(interface="vcan0")
        self.raw_stream = bus_traffic()
        self.fake_socket = FakeCanSocket(list(self.raw_stream))
        self.communication = SocketCanInterface(config.communication, socket_factory=lambda: self.fake_socket)
        self.transport = CanTransport(config.transport)
        self.listener = RecordingListener()
        self.transport.add_listener(self.listener)
        self.outcomes = self.pump()

    def pump(self) -> List[FrameOutcome]:
        """Drive the receive loop once per queued raw frame, as main.py does."""
        outcomes = []
        with self.communication:
            for _ in range(len(self.raw_stream)):
                frame = self.communication.receive()
                if frame is not None:
                    outcomes.append(self.transport.process(frame))
        return outcomes

    def diagnostics_by_id(self) -> Dict[int, List[bytes]]:
        delivered = defaultdict(list)
        for message in self.listener.messages:
            if message.message_id in DIAGNOSTIC_IDS:
                delivered[message.message_id].append(message.payload)
        return dict(delivered)

    def test_only_recovery_messages_are_delivered(self) -> None:
        expected = {can_id: [recovery_text(m)] for m, can_id in enumerate(DIAGNOSTIC_IDS)}
        self.assertEqual(self.diagnostics_by_id(), expected)

    def test_frame_accounting_excludes_noise_and_invalid_frames(self) -> None:
        noise_count = sum(1 for raw in self.raw_stream if 0x200 <= int.from_bytes(raw[:4], "little") <= 0x2FF)
        invalid_count = 1
        real_count = len(self.raw_stream) - noise_count - invalid_count
        processed = sum(outcome is not FrameOutcome.IGNORED for outcome in self.outcomes)
        self.assertEqual(processed, real_count)
        self.assertEqual(self.outcomes.count(FrameOutcome.IGNORED), noise_count)
        self.assertEqual(self.communication.invalid_frames, invalid_count)

    def test_single_frame_messages_carry_boundary_timestamp(self) -> None:
        single = [m for m in self.listener.messages if m.message_id not in DIAGNOSTIC_IDS]
        self.assertTrue(single)
        for message in single:
            self.assertIsInstance(message.metadata.received_at_ns, int)
        self.assertIn(FAULT_ID, {m.message_id for m in single})

    def test_contexts_are_idle_and_socket_released(self) -> None:
        for context in self.transport.reassembler.contexts.values():
            self.assertEqual(context.received_length, 0)
        self.assertEqual(len(self.transport.reassembler.contexts), MODULE_COUNT)
        self.assertTrue(self.fake_socket.closed)


if __name__ == "__main__":
    unittest.main()
