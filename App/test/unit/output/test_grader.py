"""Unit tests for the grader NDJSON output (ADAPTER.md contract)."""

import io
import json
import unittest

from models.application_event import DiagnosticCompleteEvent, FaultEvent, StatsEvent, TelemetryEvent
from output.grader import GraderOutput
from protocol.diagnostic import DiagnosticResult
from protocol.fault import FaultCode, FaultResult
from protocol.telemetry import TelemetryResult


class FlushCountingStream(io.StringIO):
    """StringIO that counts flushes."""

    def __init__(self) -> None:
        super().__init__()
        self.flushes = 0

    def flush(self) -> None:
        self.flushes += 1
        super().flush()


class GraderOutputTest(unittest.TestCase):
    """Each event becomes exactly one flushed JSON line with ADAPTER.md fields."""

    def setUp(self) -> None:
        self.stream = FlushCountingStream()
        self.output = GraderOutput(self.stream)

    def published_lines(self) -> list:
        return self.stream.getvalue().splitlines()

    def test_telemetry_line(self) -> None:
        # 4123 * 0.1 and 11855 * 0.01 are not exact in binary floating point.
        telemetry = TelemetryResult(0, 4821, 4123 * 0.1, 11855 * 0.01, 47, True, False, True)
        self.output.on_event(TelemetryEvent(telemetry))
        self.assertEqual(
            self.published_lines(),
            ['{"type": "telemetry", "module": 0, "seq": 4821, "voltage": 412.3, "current": 118.55, '
             '"temp_c": 47, "enabled": true, "fault": false, "derated": true}'],
        )

    def test_fault_line(self) -> None:
        self.output.on_event(FaultEvent(FaultResult(module_id=2, code=FaultCode.OVERTEMP)))
        self.assertEqual(self.published_lines(), ['{"type": "fault", "module": 2, "code": 1}'])

    def test_diag_complete_line(self) -> None:
        diagnostic = DiagnosticResult(0x6F0, 0, "SN:PMU-4471-A FW:2.3.1", "PMU-4471-A", "2.3.1")
        self.output.on_event(DiagnosticCompleteEvent(diagnostic, completed_at_ns=88123456789))
        self.assertEqual(
            self.published_lines(),
            ['{"type": "diag_complete", "can_id": "0x6f0", "string": "SN:PMU-4471-A FW:2.3.1", "ts_ns": 88123456789}'],
        )

    def test_stats_line(self) -> None:
        self.output.on_event(StatsEvent(frames_processed=15234))
        self.assertEqual(self.published_lines(), ['{"type": "stats", "frames_processed": 15234}'])

    def test_every_line_is_json_with_a_type_and_is_flushed(self) -> None:
        events = [StatsEvent(1), FaultEvent(FaultResult(1, FaultCode.ISOLATION_FAULT)), StatsEvent(2)]
        for event in events:
            self.output.on_event(event)
        lines = self.published_lines()
        self.assertEqual(len(lines), len(events))
        self.assertEqual([json.loads(line)["type"] for line in lines], ["stats", "fault", "stats"])
        self.assertEqual(self.stream.flushes, len(events))
        self.assertTrue(self.stream.getvalue().endswith("\n"))
        self.assertNotIn("\x1b", self.stream.getvalue())

    def test_each_line_parses_independently(self) -> None:
        diagnostic = DiagnosticResult(0x6F3, 3, "SN:PMU-4474-D FW:2.4.0 #1", "PMU-4474-D", "2.4.0")
        events = [
            TelemetryEvent(TelemetryResult(3, 1, 400.0, 0.0, -40, False, True, False)),
            DiagnosticCompleteEvent(diagnostic, completed_at_ns=2**63 - 1),
            StatsEvent(0),
        ]
        for event in events:
            self.output.on_event(event)
        parsed = [json.loads(line) for line in self.published_lines()]
        self.assertEqual([line["type"] for line in parsed], ["telemetry", "diag_complete", "stats"])
        self.assertTrue(all(isinstance(line, dict) for line in parsed))

    def test_diag_complete_timestamp_is_the_completion_time_unchanged(self) -> None:
        diagnostic = DiagnosticResult(0x6F1, 1, "SN:PMU-4472-B FW:2.3.1", "PMU-4472-B", "2.3.1")
        self.output.on_event(DiagnosticCompleteEvent(diagnostic, completed_at_ns=123_456_789_012_345))
        line = json.loads(self.published_lines()[0])
        self.assertEqual(line["ts_ns"], 123_456_789_012_345)
        self.assertIsInstance(line["ts_ns"], int)

    def test_non_json_values_are_refused_without_writing(self) -> None:
        for value in (float("nan"), float("inf")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.output.on_event(TelemetryEvent(TelemetryResult(0, 1, value, 1.0, 20, True, False, False)))
        self.assertEqual(self.stream.getvalue(), "")
        self.assertEqual(self.stream.flushes, 0)


if __name__ == "__main__":
    unittest.main()
