"""Integration: raw socket bytes through the application composed by ``main``.

``main.build_application`` and ``main.run`` wire the real layers exactly as the
entry point does; only the kernel socket is replaced by a fake. A queued
``KeyboardInterrupt`` stops the loop like Ctrl+C would.
"""

import contextlib
import io
import json
import signal
import unittest
from typing import Any, Dict, List
from unittest import mock

import main
from communication.socketcan import SocketCanInterface
from config.constants import DIAGNOSTIC_BASE_ID, FAULT_ID, MODULE_COUNT, NOISE_ID_FIRST, TELEMETRY_BASE_ID
from config.settings import build_application_config
from helpers import FakeCanSocket, consecutive_frame, first_frame, interleave, raw_can_frame, segment_message, to_raw
from models.can_frame import CANFrame
from output.grader import GraderOutput
from transport.can_transport import CanTransport

DIAGNOSTIC_IDS = [DIAGNOSTIC_BASE_ID + module for module in range(MODULE_COUNT)]
TELEMETRY_PAYLOAD = bytes([0x1B, 0x10, 0x4F, 0x2E, 0x57, 0x05, 0xD5, 0x12])  # 412.3 V, 118.55 A, 47 C, seq 4821


def recovery_text(module: int) -> str:
    """The clean message each module sends after its messy situation."""
    return f"SN:PMU-447{module + 1}-{'ABCD'[module]} FW:2.3.1 #{module}"


def messy_openings() -> List[List[CANFrame]]:
    """CHALLENGE.md situations 1-4, one per module, plus a repeated abandonment."""
    orphan = [consecutive_frame(DIAGNOSTIC_IDS[0], 5, bytes(7))]
    restart = segment_message(DIAGNOSTIC_IDS[1], b"XX:DECOY-NOT-REAL-MSG")[:2]
    oversized = [first_frame(DIAGNOSTIC_IDS[2], 200, bytes(6))]
    broken = segment_message(DIAGNOSTIC_IDS[3], b"SN:PMU-4474-D FW:2.4.0 #0-BROKEN")
    out_of_order = [broken[0], broken[1], consecutive_frame(DIAGNOSTIC_IDS[3], 3, broken[3].data[1:])]
    abandoned = [first_frame(DIAGNOSTIC_IDS[0], 24, b"SN:PMU")] * 3
    return [orphan + abandoned, restart, oversized, out_of_order]


def bus_traffic() -> List[bytes]:
    """Raw stream: messy openings, interleaved recoveries, telemetry, a fault and noise."""
    frames = interleave(*messy_openings())
    frames += interleave(*(segment_message(can_id, recovery_text(m).encode("ascii"))
                           for m, can_id in enumerate(DIAGNOSTIC_IDS)))
    raw = []
    for index, frame in enumerate(frames):
        raw += [to_raw(frame), raw_can_frame(NOISE_ID_FIRST + index, bytes(8))]
    raw += [raw_can_frame(TELEMETRY_BASE_ID + m, TELEMETRY_PAYLOAD) for m in range(MODULE_COUNT)]
    raw.append(raw_can_frame(FAULT_ID, bytes([2, 1, 0, 0, 0, 0, 0, 0])))
    return raw


def real_frame_count(raw_stream: List[bytes]) -> int:
    """Frames on telemetry, fault or diagnostic IDs."""
    return sum(1 for raw in raw_stream if not 0x200 <= int.from_bytes(raw[:4], "little") <= 0x2FF)


class ComposedApplicationTest(unittest.TestCase):
    """Both modes run the same composed application over the same traffic."""

    def setUp(self) -> None:
        previous = signal.getsignal(signal.SIGTERM)
        self.addCleanup(signal.signal, signal.SIGTERM, previous)
        self.raw_stream = bus_traffic()

    def run_application(self, grader: bool) -> str:
        """Run ``main.run`` over the traffic and return everything written to stdout."""
        config = build_application_config(interface="vcan0", grader=grader)
        fake_socket = FakeCanSocket(list(self.raw_stream) + [KeyboardInterrupt()])
        communication = SocketCanInterface(config.communication, socket_factory=lambda: fake_socket)
        transport = CanTransport(config.transport)
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            application = main.build_application(config, transport)
            self.assertEqual(main.run(application, communication, transport), 0)
        self.assertTrue(fake_socket.closed)
        return stdout.getvalue()

    def grader_events(self) -> List[Dict[str, Any]]:
        return [json.loads(line) for line in self.run_application(grader=True).splitlines()]

    def test_grader_reports_only_recovery_messages(self) -> None:
        completions = [e for e in self.grader_events() if e["type"] == "diag_complete"]
        expected = {f"{can_id:#x}": recovery_text(m) for m, can_id in enumerate(DIAGNOSTIC_IDS)}
        self.assertEqual({e["can_id"]: e["string"] for e in completions}, expected)
        self.assertEqual(len(completions), MODULE_COUNT)
        timestamps = [e["ts_ns"] for e in completions]
        self.assertTrue(all(isinstance(ts, int) for ts in timestamps))
        self.assertEqual(timestamps, sorted(timestamps))

    def test_grader_reports_telemetry_and_faults(self) -> None:
        events = self.grader_events()
        telemetry = [e for e in events if e["type"] == "telemetry"]
        self.assertEqual([e["module"] for e in telemetry], list(range(MODULE_COUNT)))
        self.assertEqual(telemetry[0], {"type": "telemetry", "module": 0, "seq": 4821, "voltage": 412.3,
                                        "current": 118.55, "temp_c": 47, "enabled": True, "fault": False,
                                        "derated": True})
        self.assertEqual([e for e in events if e["type"] == "fault"], [{"type": "fault", "module": 2, "code": 1}])

    def test_grader_final_stats_count_real_frames_only(self) -> None:
        events = self.grader_events()
        stats = [e for e in events if e["type"] == "stats"]
        self.assertGreaterEqual(len(stats), 2)
        self.assertEqual(events[-1], {"type": "stats", "frames_processed": real_frame_count(self.raw_stream)})

    def test_a_broken_output_stops_with_an_error_and_still_closes_the_bus(self) -> None:
        config = build_application_config(interface="vcan0", grader=True)
        fake_socket = FakeCanSocket(list(self.raw_stream))
        communication = SocketCanInterface(config.communication, socket_factory=lambda: fake_socket)
        transport = CanTransport(config.transport)
        application = main.build_application(config, transport)
        with mock.patch.object(GraderOutput, "on_event", side_effect=OSError("stdout closed")), \
                self.assertLogs(level="ERROR") as logs:
            self.assertEqual(main.run(application, communication, transport), 1)
        self.assertTrue(fake_socket.closed)
        self.assertTrue(any("final stats not delivered" in line for line in logs.output))

    def test_normal_mode_draws_the_dashboard_from_the_same_events(self) -> None:
        output = self.run_application(grader=False)
        final_frame = output.rsplit("\x1b[H", 1)[-1]
        for module, can_id in enumerate(DIAGNOSTIC_IDS):
            self.assertIn(f"{can_id:#x}: {recovery_text(module)}", final_frame)
        self.assertIn("Module 0:  412.3V  118.55A   47C", final_frame)
        self.assertIn("module 2, code 1 (overtemp)", final_frame)
        self.assertIn(f"Frames processed: {real_frame_count(self.raw_stream)}", final_frame)


if __name__ == "__main__":
    unittest.main()
