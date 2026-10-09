"""End-to-end: live challenge generator -> vcan0 -> SocketCAN -> CanTransport.

Runs the read-only challenge generator unmodified, receives its traffic on the
real interface, and checks the result against the generator's own ground-truth
log. Our code only receives; the generator is the only transmitter.

Skipped unless SocketCAN, the interface and the generator are all available
(i.e. on the Raspberry Pi). Environment overrides:

* ``DEEPSEA_CAN_IFACE``     interface name (default ``vcan0``)
* ``DEEPSEA_GENERATOR``     generator path (default ``~/challenge/can_generator/generator.py``)
* ``DEEPSEA_E2E_DURATION``  generator run time in seconds (default ``20``)

The ground-truth file is written to a temporary directory and deleted afterwards.
"""

import json
import os
import pathlib
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from collections import defaultdict
from typing import Dict, List, Optional

from communication.socketcan import SocketCanInterface
from config.constants import MODULE_COUNT
from config.settings import build_application_config
from helpers import RecordingListener
from models.message import FramingMode
from transport.can_transport import CanTransport
from transport.transport import FrameOutcome

INTERFACE = os.environ.get("DEEPSEA_CAN_IFACE", "vcan0")
GENERATOR = pathlib.Path(os.environ.get("DEEPSEA_GENERATOR", "~/challenge/can_generator/generator.py")).expanduser()
DURATION_S = float(os.environ.get("DEEPSEA_E2E_DURATION", "20"))
SAFETY_MARGIN_S = 30.0


def skip_reason() -> Optional[str]:
    """Explain why the live test cannot run here, or return None if it can."""
    if not hasattr(socket, "AF_CAN"):
        return "SocketCAN is not available on this platform"
    if not pathlib.Path("/sys/class/net", INTERFACE).exists():
        return f"CAN interface {INTERFACE} is not present"
    if not GENERATOR.is_file():
        return f"challenge generator not found at {GENERATOR}"
    return None


SKIP_REASON = skip_reason()


@unittest.skipIf(SKIP_REASON is not None, SKIP_REASON or "")
class GeneratorOnLiveBusTest(unittest.TestCase):
    """One generator run shared by every assertion in this class."""

    @classmethod
    def setUpClass(cls) -> None:
        config = build_application_config(interface=INTERFACE)
        cls.transport = CanTransport(config.transport)
        cls.listener = RecordingListener()
        cls.transport.add_listener(cls.listener)
        cls.frames_processed = 0
        with tempfile.TemporaryDirectory() as temp_dir:
            ground_truth = pathlib.Path(temp_dir) / "ground_truth.jsonl"
            with SocketCanInterface(config.communication) as communication:
                cls.generator_exit_code = cls._run_generator(communication, ground_truth)
            cls.events = [json.loads(line) for line in ground_truth.read_text().splitlines() if line]

    @classmethod
    def _run_generator(cls, communication: SocketCanInterface, ground_truth: pathlib.Path) -> int:
        """Start the generator, receive until it exits, then drain the socket."""
        command = [sys.executable, str(GENERATOR), "--iface", INTERFACE,
                   "--duration", str(DURATION_S), "--out", str(ground_truth)]
        deadline = time.monotonic() + DURATION_S + SAFETY_MARGIN_S
        process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            while process.poll() is None and time.monotonic() < deadline:
                cls._receive_one(communication)
            while cls._receive_one(communication):
                pass
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
        return process.returncode

    @classmethod
    def _receive_one(cls, communication: SocketCanInterface) -> bool:
        """Receive and process one frame; False when the receive timed out."""
        frame = communication.receive()
        if frame is None:
            return False
        if cls.transport.process(frame) is not FrameOutcome.IGNORED:
            cls.frames_processed += 1
        return True

    def ground_truth(self, event: str) -> List[dict]:
        return [record for record in self.events if record["event"] == event]

    def received_diagnostics(self) -> Dict[str, List[str]]:
        received = defaultdict(list)
        for message in self.listener.messages:
            if message.metadata.framing is FramingMode.SEGMENTED:
                received[hex(message.message_id)].append(message.payload.decode("ascii"))
        return dict(received)

    def test_generator_ran_to_completion(self) -> None:
        self.assertEqual(self.generator_exit_code, 0)
        self.assertEqual(len(self.ground_truth("run_summary")), 1)

    def test_frames_processed_matches_real_traffic_count(self) -> None:
        summary = self.ground_truth("run_summary")[0]
        self.assertEqual(self.frames_processed, summary["real_frame_count"])

    def test_every_diagnostic_message_matches_ground_truth_in_order(self) -> None:
        expected = defaultdict(list)
        for record in self.ground_truth("diag_complete_sent"):
            expected[record["can_id"]].append(record["string"])
        self.assertEqual(self.received_diagnostics(), dict(expected))

    def test_all_messy_situations_occurred(self) -> None:
        cases = {record["case"] for record in self.ground_truth("diag_situation")}
        self.assertEqual(cases, {"orphan_cf", "restart_ff", "oversized_len", "out_of_order"})

    def test_single_frame_messages_match_sent_count(self) -> None:
        sent = len(self.ground_truth("telemetry_sent")) + len(self.ground_truth("fault_sent"))
        single = [m for m in self.listener.messages if m.metadata.framing is FramingMode.SINGLE_FRAME]
        self.assertEqual(len(single), sent)

    def test_reassembly_state_stayed_bounded(self) -> None:
        contexts = self.transport.reassembler.contexts
        self.assertEqual(len(contexts), MODULE_COUNT)
        for context in contexts.values():
            self.assertLessEqual(context.received_length, context.max_length)


if __name__ == "__main__":
    unittest.main()
