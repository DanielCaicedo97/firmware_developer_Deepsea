"""CanTransport output dispatched through the challenge routes to the controllers."""

import struct
import unittest
from typing import List

from config.constants import DIAGNOSTIC_BASE_ID, FAULT_ID, MODULE_COUNT, NOISE_ID_FIRST, TELEMETRY_BASE_ID
from config.settings import TransportConfig, build_framing_map
from helpers import RecordingController, RecordingListener, consecutive_frame, first_frame, interleave, segment_message
from models.can_frame import CANFrame
from protocol.diagnostic import DiagnosticResult
from protocol.fault import FaultCode, FaultResult
from protocol.telemetry import TelemetryResult
from routes.common import DispatchResult, DispatchStatus
from routes.routes_init import init_routes
from transport.can_transport import CanTransport


class TransportToRouterTest(unittest.TestCase):
    """Generator-shaped traffic through the transport, then the root router."""

    def setUp(self) -> None:
        self.transport = CanTransport(TransportConfig(framing=build_framing_map()))
        self.listener = RecordingListener()
        self.transport.add_listener(self.listener)
        self.controllers = [RecordingController(), RecordingController(), RecordingController()]
        self.root = init_routes(*self.controllers)

    def dispatch_frames(self, frames: List[CANFrame]) -> List[DispatchResult]:
        """Process frames through the transport and dispatch every complete message."""
        for frame in frames:
            self.transport.process(frame)
        return [self.root.dispatch(message) for message in self.listener.messages]

    def test_mixed_traffic_reaches_the_right_controllers(self) -> None:
        texts = [f"SN:PMU-447{m + 1} FW:2.3.1 #{m}" for m in range(MODULE_COUNT)]
        diagnostics = interleave(*(segment_message(DIAGNOSTIC_BASE_ID + m, texts[m].encode("ascii"))
                                   for m in range(MODULE_COUNT)))
        frames = [
            CANFrame(can_id=TELEMETRY_BASE_ID + 1, data=struct.pack("<HHBBH", 4123, 11855, 87, 0x01, 7)),
            CANFrame(can_id=NOISE_ID_FIRST, data=bytes(8)),
            CANFrame(can_id=FAULT_ID, data=bytes([3, 2, 0, 0, 0, 0, 0, 0])),
        ] + diagnostics
        dispatched = self.dispatch_frames(frames)

        self.assertTrue(all(d.status is DispatchStatus.SUCCESS for d in dispatched))
        by_router = {name: [d.result.decoded for d in dispatched if d.router_name == name]
                     for name in ("telemetry", "fault", "diagnostic")}
        telemetry, = by_router["telemetry"]
        self.assertIsInstance(telemetry, TelemetryResult)
        self.assertEqual((telemetry.module_id, telemetry.sequence), (1, 7))
        self.assertEqual(by_router["fault"], [FaultResult(module_id=3, code=FaultCode.OVERVOLTAGE)])
        diagnostic_results = by_router["diagnostic"]
        self.assertTrue(all(isinstance(r, DiagnosticResult) for r in diagnostic_results))
        self.assertEqual(sorted((r.module_id, r.text) for r in diagnostic_results), list(enumerate(texts)))
        self.assertEqual([len(c.handled) for c in self.controllers], [1, 1, MODULE_COUNT])

    def test_abandoned_reassembly_reaches_no_decoder(self) -> None:
        decoy = b"XX:DECOY-NOT-REAL-MSG"
        dispatched = self.dispatch_frames([first_frame(DIAGNOSTIC_BASE_ID, len(decoy), decoy[:6]),
                                           consecutive_frame(DIAGNOSTIC_BASE_ID, 1, decoy[6:13])])
        self.assertEqual(dispatched, [])
        self.assertEqual([len(c.handled) for c in self.controllers], [0, 0, 0])

    def test_malformed_payload_fails_and_routing_continues(self) -> None:
        dispatched = self.dispatch_frames([
            CANFrame(can_id=FAULT_ID, data=bytes([0, 7, 0, 0, 0, 0, 0, 0])),
            CANFrame(can_id=FAULT_ID, data=bytes([0, 1, 0, 0, 0, 0, 0, 0])),
        ])
        self.assertEqual([d.status for d in dispatched], [DispatchStatus.HANDLER_FAILED, DispatchStatus.SUCCESS])


if __name__ == "__main__":
    unittest.main()
