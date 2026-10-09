"""Integration: stdout/stderr separation of both modes in a real child process.

The child composes the application exactly as ``main.main`` does (with debug
logging on), but feeds a fake socket instead of ``vcan0``. A queued
``KeyboardInterrupt`` stops it like Ctrl+C. No CAN hardware is needed.
"""

import json
import subprocess
import sys
import unittest
from pathlib import Path
from typing import List

SRC_DIR = Path(__file__).resolve().parents[3] / "src"
TEST_DIR = Path(__file__).resolve().parents[2]
TIMEOUT_S = 60
REAL_FRAME_COUNT = 4 + 1 + 4  # telemetry + fault + the 4 frames of the identification string

CHILD_SCRIPT = """
import sys
sys.path[:0] = [sys.argv[1], sys.argv[2]]
import main
from communication.socketcan import SocketCanInterface
from config.settings import build_application_config
from helpers import FakeCanSocket, raw_can_frame, segment_message, to_raw
from transport.can_transport import CanTransport

config = build_application_config(interface="vcan0", debug=True, grader=sys.argv[3] == "grader")
main.configure_logging(config.logging)
raw = [raw_can_frame(0x100 + m, bytes([0x1B, 0x10, 0x4F, 0x2E, 0x57, 0x05, 0xD5, 0x12])) for m in range(4)]
raw.append(raw_can_frame(0x1F0, bytes([2, 1, 0, 0, 0, 0, 0, 0])))
raw += [to_raw(f) for f in segment_message(0x6F0, b"SN:PMU-4471-A FW:2.3.1 #0")]
raw += [raw_can_frame(0x200 + n, bytes(8)) for n in range(10)]
fake = FakeCanSocket(raw + [KeyboardInterrupt()])
communication = SocketCanInterface(config.communication, socket_factory=lambda: fake)
transport = CanTransport(config.transport)
sys.exit(main.run(main.build_application(config, transport), communication, transport))
"""


def run_child(mode: str) -> subprocess.CompletedProcess:
    """Run the composed application in a child process in ``mode`` and capture its streams."""
    return subprocess.run(
        [sys.executable, "-c", CHILD_SCRIPT, str(SRC_DIR), str(TEST_DIR), mode],
        capture_output=True, text=True, timeout=TIMEOUT_S, check=False,
    )


class GraderStreamTest(unittest.TestCase):
    """``--grader``: stdout carries only flushed NDJSON; logs go to stderr."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.result = run_child("grader")

    def lines(self) -> List[str]:
        return self.result.stdout.splitlines()

    def test_exits_cleanly(self) -> None:
        self.assertEqual(self.result.returncode, 0, self.result.stderr)

    def test_every_stdout_line_is_an_independent_json_object(self) -> None:
        self.assertTrue(self.lines())
        for line in self.lines():
            with self.subTest(line=line):
                parsed = json.loads(line)
                self.assertIsInstance(parsed, dict)
                self.assertIn(parsed["type"], {"telemetry", "fault", "diag_complete", "stats"})
        self.assertTrue(self.result.stdout.endswith("\n"))
        self.assertNotIn("\x1b", self.result.stdout)

    def test_emits_each_event_type_and_ends_with_the_final_stats(self) -> None:
        parsed = [json.loads(line) for line in self.lines()]
        self.assertEqual(sum(1 for e in parsed if e["type"] == "telemetry"), 4)
        self.assertEqual([e for e in parsed if e["type"] == "fault"], [{"type": "fault", "module": 2, "code": 1}])
        completions = [e for e in parsed if e["type"] == "diag_complete"]
        self.assertEqual([(e["can_id"], e["string"]) for e in completions], [("0x6f0", "SN:PMU-4471-A FW:2.3.1 #0")])
        self.assertIsInstance(completions[0]["ts_ns"], int)
        self.assertEqual(parsed[-1], {"type": "stats", "frames_processed": REAL_FRAME_COUNT})

    def test_logs_go_to_stderr_not_stdout(self) -> None:
        self.assertIn("interrupted, shutting down", self.result.stderr)
        self.assertNotIn("interrupted", self.result.stdout)
        self.assertNotIn("DEBUG", self.result.stdout)


class NormalModeStreamTest(unittest.TestCase):
    """Normal mode: the dashboard on stdout, logs on stderr."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.result = run_child("normal")

    def test_draws_the_dashboard_and_exits_cleanly(self) -> None:
        self.assertEqual(self.result.returncode, 0, self.result.stderr)
        final_frame = self.result.stdout.rsplit("\x1b[H", 1)[-1]
        self.assertIn("0x6f0: SN:PMU-4471-A FW:2.3.1 #0", final_frame)
        self.assertIn(f"Frames processed: {REAL_FRAME_COUNT}", final_frame)

    def test_logs_go_to_stderr_not_stdout(self) -> None:
        self.assertIn("interrupted, shutting down", self.result.stderr)
        self.assertNotIn("interrupted", self.result.stdout)


class EntryPointFailureTest(unittest.TestCase):
    """``main.py --grader`` on an unusable interface writes nothing to stdout."""

    def test_unusable_interface_fails_on_stderr_only(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SRC_DIR / "main.py"), "--iface", "deepsea-missing0", "--grader"],
            capture_output=True, text=True, timeout=TIMEOUT_S, check=False,
        )
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("ERROR", result.stderr)


if __name__ == "__main__":
    unittest.main()
