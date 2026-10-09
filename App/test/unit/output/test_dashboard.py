"""Unit tests for the normal-mode terminal dashboard."""

import ast
import io
import unittest
from pathlib import Path

from helpers import FakeClock
from models.application_event import DiagnosticCompleteEvent, FaultEvent, StatsEvent, TelemetryEvent
import output.dashboard
from output.dashboard import CURSOR_HOME, Dashboard, format_dashboard
from protocol.diagnostic import DiagnosticResult
from protocol.fault import FaultCode, FaultResult
from protocol.telemetry import TelemetryResult
from services.application_state import ApplicationState

REFRESH_NS = 100
TELEMETRY = TelemetryResult(0, 4821, 412.3, 118.55, 47, True, False, False)


class FormatDashboardTest(unittest.TestCase):
    """The dashboard text reflects the application state."""

    def test_empty_state_shows_placeholders(self) -> None:
        text = "\n".join(format_dashboard(ApplicationState().snapshot(), 0))
        self.assertIn("DeepSea CAN Diagnostic Tool", text)
        self.assertEqual(text.count("(no telemetry yet)"), 4)
        self.assertEqual(text.count("(not yet received)"), 4)
        self.assertIn("(none)", text)
        self.assertIn("Frames processed: 0", text)

    def test_populated_state(self) -> None:
        state = ApplicationState()
        state.update_telemetry(TELEMETRY)
        state.update_identification(DiagnosticResult(0x6F2, 2, "SN:PMU-4473-C FW:2.4.0", "PMU-4473-C", "2.4.0"), 1)
        state.record_fault(FaultResult(2, FaultCode.OVERTEMP))
        text = "\n".join(format_dashboard(state.snapshot(), 42))
        self.assertIn("Module 0:  412.3V  118.55A   47C   enabled=True  fault=False", text)
        self.assertIn("0x6f2: SN:PMU-4473-C FW:2.4.0", text)
        self.assertIn("module 2, code 1 (overtemp)", text)
        self.assertIn("Frames processed: 42", text)

    def test_partial_state_shows_placeholders_only_where_missing(self) -> None:
        state = ApplicationState()
        state.update_telemetry(TELEMETRY)
        text = "\n".join(format_dashboard(state.snapshot(), 3))
        self.assertIn("Module 0:  412.3V", text)
        self.assertEqual(text.count("(no telemetry yet)"), 3)
        self.assertEqual(text.count("(not yet received)"), 4)

    def test_does_not_decode_or_touch_the_bus(self) -> None:
        tree = ast.parse(Path(output.dashboard.__file__).read_text(encoding="utf-8"))
        imported = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
        imported |= {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
        forbidden = ("socket", "struct", "communication", "transport", "routes", "controllers")
        self.assertEqual([m for m in imported if m and m.split(".")[0] in forbidden], [])
        self.assertFalse(any(m and m.startswith("protocol.") and not m.endswith(".models") for m in imported))


class DashboardTest(unittest.TestCase):
    """Redraw scheduling and in-place drawing."""

    def setUp(self) -> None:
        self.state = ApplicationState()
        self.stream = io.StringIO()
        self.clock = FakeClock()
        self.dashboard = Dashboard(self.state, self.stream, REFRESH_NS, self.clock)

    def redraws(self) -> int:
        return self.stream.getvalue().count(CURSOR_HOME)

    def test_draws_in_place_without_scrolling(self) -> None:
        self.dashboard.on_event(StatsEvent(7))
        output = self.stream.getvalue()
        self.assertTrue(output.startswith(CURSOR_HOME))
        self.assertIn("Frames processed: 7", output)

    def test_throttles_redraws_between_stats(self) -> None:
        self.dashboard.on_event(TelemetryEvent(TELEMETRY))
        self.dashboard.on_event(FaultEvent(FaultResult(0, FaultCode.OVERTEMP)))
        self.assertEqual(self.redraws(), 1)
        self.clock.now = REFRESH_NS
        self.dashboard.on_event(TelemetryEvent(TELEMETRY))
        self.assertEqual(self.redraws(), 2)

    def test_renders_the_state_the_controllers_stored(self) -> None:
        diagnostic = DiagnosticResult(0x6F1, 1, "SN:PMU-4472-B FW:2.3.1", "PMU-4472-B", "2.3.1")
        self.state.update_identification(diagnostic, 5)
        self.dashboard.on_event(DiagnosticCompleteEvent(diagnostic, completed_at_ns=5))
        self.assertIn("0x6f1: SN:PMU-4472-B FW:2.3.1", self.stream.getvalue())

    def test_stats_always_redraw(self) -> None:
        self.dashboard.on_event(StatsEvent(1))
        self.dashboard.on_event(StatsEvent(2))
        self.assertEqual(self.redraws(), 2)


if __name__ == "__main__":
    unittest.main()
