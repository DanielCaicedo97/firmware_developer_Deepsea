"""Messages delivered by CanTransport decode with the Feature 02 decoders.

The test chooses the decoder itself; it stands in for the future router only
to prove the transport output and the decoder input are compatible.
"""

import struct
import unittest
from typing import List

from config.constants import DIAGNOSTIC_BASE_ID, FAULT_ID, MODULE_COUNT, TELEMETRY_BASE_ID
from config.settings import TransportConfig, build_framing_map
from helpers import RecordingListener, consecutive_frame, first_frame, interleave, segment_message
from models.can_frame import CANFrame
from protocol.fault import FaultCode
from protocol.diagnostic import decode_diagnostic
from protocol.fault import decode_fault
from protocol.telemetry import decode_telemetry
from transport.can_transport import CanTransport

GENERATOR_STRINGS = [
    "SN:PMU-4471-A FW:2.3.1",
    "SN:PMU-4472-B FW:2.3.1",
    "SN:PMU-4473-C FW:2.4.0",
    "SN:PMU-4474-D FW:2.4.0",
]


class TransportToDecodersTest(unittest.TestCase):
    """Generator-shaped traffic through the transport, then each decoder."""

    def setUp(self) -> None:
        self.transport = CanTransport(TransportConfig(framing=build_framing_map()))
        self.listener = RecordingListener()
        self.transport.add_listener(self.listener)

    def feed(self, frames: List[CANFrame]) -> None:
        """Process every frame through the transport, in order."""
        for frame in frames:
            self.transport.process(frame)

    def test_interleaved_identification_strings_decode_per_module(self) -> None:
        texts = [f"{GENERATOR_STRINGS[m]} #{m + 3}" for m in range(MODULE_COUNT)]
        self.feed(interleave(*(segment_message(DIAGNOSTIC_BASE_ID + m, texts[m].encode("ascii"))
                               for m in range(MODULE_COUNT))))
        results = [decode_diagnostic(message) for message in self.listener.messages]
        self.assertEqual(sorted((r.module_id, r.text) for r in results), list(enumerate(texts)))

    def test_recovery_message_after_restart_decodes(self) -> None:
        decoy = b"XX:DECOY-NOT-REAL-MSG"
        self.feed([first_frame(DIAGNOSTIC_BASE_ID, len(decoy), decoy[:6]),
                   consecutive_frame(DIAGNOSTIC_BASE_ID, 1, decoy[6:13])])
        self.feed(segment_message(DIAGNOSTIC_BASE_ID, b"SN:PMU-4471-A FW:2.3.1 #9"))
        self.assertEqual(len(self.listener.messages), 1)
        self.assertEqual(decode_diagnostic(self.listener.messages[0]).counter, 9)

    def test_telemetry_and_fault_frames_decode(self) -> None:
        payload = struct.pack("<HHBBH", 4123, 11855, 87, 0x01, 4821)
        self.feed([CANFrame(can_id=TELEMETRY_BASE_ID + 3, data=payload),
                   CANFrame(can_id=0x2A0, data=bytes(8)),
                   CANFrame(can_id=FAULT_ID, data=bytes([2, 1, 0, 0, 0, 0, 0, 0]))])
        telemetry_message, fault_message = self.listener.messages
        telemetry = decode_telemetry(telemetry_message)
        self.assertEqual((telemetry.module_id, telemetry.sequence, telemetry.temperature_c), (3, 4821, 47))
        fault = decode_fault(fault_message)
        self.assertEqual((fault.module_id, fault.code), (2, FaultCode.OVERTEMP))


if __name__ == "__main__":
    unittest.main()
