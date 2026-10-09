"""Unit tests for the telemetry, fault and diagnostic controllers (spec 05 §9)."""

import ast
import contextlib
import io
import pathlib
import unittest
from unittest import mock

import controllers
from config.constants import DIAGNOSTIC_BASE_ID, FAULT_ID, MODULE_COUNT, TELEMETRY_BASE_ID
from controllers.base_controller import BaseController
from controllers.diagnostic import DiagnosticController
from controllers.fault import FaultController
from controllers.results import ControllerStatus
from controllers.telemetry import TelemetryController
from helpers import STATS_INTERVAL_NS, RecordingPublisher, complete_message
from models.application_event import DiagnosticCompleteEvent, EventType, FaultEvent, TelemetryEvent
from models.message import FramingMode, Message
from protocol.diagnostic import DiagnosticResult
from protocol.fault import FaultCode, FaultResult
from protocol.telemetry import TelemetryResult
from services.application_state import ApplicationState
from services.stats_service import StatsService

TELEMETRY = TelemetryResult(2, 4821, 412.3, 118.55, 47, True, False, True)
FAULT = FaultResult(module_id=2, code=FaultCode.OVERTEMP)
IDENTIFICATION = DiagnosticResult(DIAGNOSTIC_BASE_ID + 1, 1, "SN:PMU-4472-B FW:2.3.1 #7", "PMU-4472-B", "2.3.1", 7)
COMPLETED_AT_NS = 88123456789


def telemetry_message(module_id: int = 2) -> Message:
    return complete_message(TELEMETRY_BASE_ID + module_id, b"")


def diagnostic_message(can_id: int = DIAGNOSTIC_BASE_ID + 1, completed_at_ns: object = COMPLETED_AT_NS) -> Message:
    return complete_message(can_id, b"", FramingMode.SEGMENTED, completed_at_ns=completed_at_ns)


class ControllerTestCase(unittest.TestCase):
    """Real state and stats with a recording publisher."""

    def setUp(self) -> None:
        self.state = ApplicationState()
        self.stats = StatsService(STATS_INTERVAL_NS)
        self.publisher = RecordingPublisher()

    def assert_counts(self, domain: EventType, processed: int, rejected: int) -> None:
        self.assertEqual((self.stats.processed(domain), self.stats.rejected(domain)), (processed, rejected))


class BaseContractTest(ControllerTestCase):
    """Shared contract, dependency injection and isolation from the bus and terminal."""

    def test_controllers_share_the_base_contract(self) -> None:
        for controller_type in (TelemetryController, FaultController, DiagnosticController):
            self.assertIsInstance(controller_type(self.state, self.stats, self.publisher), BaseController)

    def test_base_controller_is_abstract(self) -> None:
        with self.assertRaises(TypeError):
            BaseController(self.state, self.stats, self.publisher)  # type: ignore[abstract]

    def test_controllers_write_nothing_to_stdout(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            TelemetryController(self.state, self.stats, self.publisher).handle(TELEMETRY, telemetry_message())
            FaultController(self.state, self.stats, self.publisher).handle(FAULT, complete_message(FAULT_ID, b""))
            diagnostic = DiagnosticController(self.state, self.stats, self.publisher)
            diagnostic.handle(IDENTIFICATION, diagnostic_message())
            diagnostic.handle(IDENTIFICATION, diagnostic_message(completed_at_ns=None))
        self.assertEqual(stdout.getvalue(), "")

    def test_controller_sources_have_no_can_io_terminal_or_output_dependencies(self) -> None:
        forbidden_imports = (
            "socket", "sys", "communication", "transport.can_transport", "output", "routes.routes_init",
        )
        forbidden_calls = {"print", "send", "sendto", "write"}
        for path in pathlib.Path(controllers.__file__).parent.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    names = [node.module or ""] if isinstance(node, ast.ImportFrom) else [a.name for a in node.names]
                    for name in names:
                        self.assertFalse(name.split(".")[0] in forbidden_imports or name in forbidden_imports,
                                         f"{path.name} imports {name}")
                if isinstance(node, ast.Call):
                    func = node.func
                    called = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
                    self.assertNotIn(called, forbidden_calls, f"{path.name} calls {called}")


class TelemetryControllerTest(ControllerTestCase):
    """TelemetryController: 0x100-0x103 decoded results."""

    def setUp(self) -> None:
        super().setUp()
        self.controller = TelemetryController(self.state, self.stats, self.publisher)

    def test_valid_result_updates_state_publishes_and_counts(self) -> None:
        outcome = self.controller.handle(TELEMETRY, telemetry_message())
        self.assertIs(outcome.status, ControllerStatus.PROCESSED)
        self.assertTrue(outcome.succeeded)
        self.assertIs(outcome.decoded, TELEMETRY)
        self.assertEqual(outcome.event, TelemetryEvent(telemetry=TELEMETRY))
        self.assertIs(self.state.telemetry(2), TELEMETRY)
        self.assertEqual(self.publisher.events, [TelemetryEvent(telemetry=TELEMETRY)])
        self.assert_counts(EventType.TELEMETRY, 1, 0)

    def test_state_is_updated_through_application_state(self) -> None:
        state = mock.create_autospec(ApplicationState, instance=True, module_count=MODULE_COUNT)
        TelemetryController(state, self.stats, self.publisher).handle(TELEMETRY, telemetry_message())
        state.update_telemetry.assert_called_once_with(TELEMETRY)

    def test_invalid_results_keep_the_last_valid_state(self) -> None:
        self.controller.handle(TELEMETRY, telemetry_message())
        out_of_range = TelemetryResult(MODULE_COUNT, 1, 400.0, 1.0, 20, True, False, False)
        mismatched = TelemetryResult(3, 1, 400.0, 1.0, 20, True, False, False)
        for result, message in ((out_of_range, telemetry_message(0)), (mismatched, telemetry_message(2))):
            outcome = self.controller.handle(result, message)
            self.assertIs(outcome.status, ControllerStatus.REJECTED)
            self.assertIsNone(outcome.event)
            self.assertTrue(outcome.reason)
        self.assertIs(self.state.telemetry(2), TELEMETRY)
        self.assertIsNone(self.state.telemetry(3))
        self.assertEqual(len(self.publisher.events), 1)
        self.assert_counts(EventType.TELEMETRY, 1, 2)

    def test_invalid_result_does_not_block_the_next_valid_one(self) -> None:
        bad = TelemetryResult(MODULE_COUNT, 1, 400.0, 1.0, 20, True, False, False)
        self.controller.handle(bad, telemetry_message(0))
        outcome = self.controller.handle(TELEMETRY, telemetry_message())
        self.assertTrue(outcome.succeeded)
        self.assertEqual(self.publisher.events, [TelemetryEvent(telemetry=TELEMETRY)])

    def test_state_failure_propagates_without_publishing_or_counting(self) -> None:
        with mock.patch.object(self.state, "update_telemetry", side_effect=RuntimeError("state broken")):
            with self.assertRaises(RuntimeError):
                self.controller.handle(TELEMETRY, telemetry_message())
        self.assertEqual(self.publisher.events, [])
        self.assert_counts(EventType.TELEMETRY, 0, 0)

    def test_publisher_failure_propagates_without_counting(self) -> None:
        publisher = mock.Mock(**{"publish.side_effect": OSError("stdout closed")})
        with self.assertRaises(OSError):
            TelemetryController(self.state, self.stats, publisher).handle(TELEMETRY, telemetry_message())
        self.assert_counts(EventType.TELEMETRY, 0, 0)


class FaultControllerTest(ControllerTestCase):
    """FaultController: 0x1F0 decoded results."""

    def setUp(self) -> None:
        super().setUp()
        self.controller = FaultController(self.state, self.stats, self.publisher)
        self.message = complete_message(FAULT_ID, b"")

    def test_valid_result_updates_state_publishes_and_counts(self) -> None:
        outcome = self.controller.handle(FAULT, self.message)
        self.assertIs(outcome.status, ControllerStatus.PROCESSED)
        self.assertEqual(outcome.event, FaultEvent(fault=FAULT))
        self.assertEqual(self.state.recent_faults, (FAULT,))
        self.assertEqual(self.publisher.events, [FaultEvent(fault=FAULT)])
        self.assert_counts(EventType.FAULT, 1, 0)

    def test_state_is_updated_through_application_state(self) -> None:
        state = mock.create_autospec(ApplicationState, instance=True, module_count=MODULE_COUNT)
        FaultController(state, self.stats, self.publisher).handle(FAULT, self.message)
        state.record_fault.assert_called_once_with(FAULT)

    def test_invalid_results_do_not_reach_state(self) -> None:
        unknown_module = FaultResult(module_id=MODULE_COUNT, code=FaultCode.OVERTEMP)
        unknown_code = FaultResult(module_id=1, code=9)  # type: ignore[arg-type]
        for result in (unknown_module, unknown_code):
            outcome = self.controller.handle(result, self.message)
            self.assertIs(outcome.status, ControllerStatus.REJECTED)
        self.assertEqual(self.state.recent_faults, ())
        self.assertEqual(self.publisher.events, [])
        self.assert_counts(EventType.FAULT, 0, 2)

    def test_invalid_result_does_not_block_the_next_valid_one(self) -> None:
        self.controller.handle(FaultResult(module_id=-1, code=FaultCode.OVERTEMP), self.message)
        self.assertTrue(self.controller.handle(FAULT, self.message).succeeded)
        self.assertEqual(self.state.recent_faults, (FAULT,))

    def test_state_failure_propagates_without_publishing_or_counting(self) -> None:
        with mock.patch.object(self.state, "record_fault", side_effect=RuntimeError("state broken")):
            with self.assertRaises(RuntimeError):
                self.controller.handle(FAULT, self.message)
        self.assertEqual(self.publisher.events, [])
        self.assert_counts(EventType.FAULT, 0, 0)


class DiagnosticControllerTest(ControllerTestCase):
    """DiagnosticController: completed 0x6F0-0x6F3 messages."""

    def setUp(self) -> None:
        super().setUp()
        self.controller = DiagnosticController(self.state, self.stats, self.publisher)

    def test_valid_result_updates_state_publishes_diag_complete_and_counts(self) -> None:
        outcome = self.controller.handle(IDENTIFICATION, diagnostic_message())
        expected = DiagnosticCompleteEvent(diagnostic=IDENTIFICATION, completed_at_ns=COMPLETED_AT_NS)
        self.assertIs(outcome.status, ControllerStatus.PROCESSED)
        self.assertEqual(outcome.event, expected)
        self.assertIs(outcome.event.event_type, EventType.DIAG_COMPLETE)
        self.assertIs(self.state.identification(1), IDENTIFICATION)
        self.assertEqual(self.publisher.events, [expected])
        self.assert_counts(EventType.DIAG_COMPLETE, 1, 0)

    def test_preserves_the_reassembly_timestamp_instead_of_reading_a_clock(self) -> None:
        with mock.patch("time.monotonic_ns", return_value=1), mock.patch("time.time_ns", return_value=2):
            self.controller.handle(IDENTIFICATION, diagnostic_message())
        self.assertEqual(self.publisher.events[0].completed_at_ns, COMPLETED_AT_NS)

    def test_state_is_updated_through_application_state(self) -> None:
        state = mock.create_autospec(ApplicationState, instance=True, module_count=MODULE_COUNT)
        DiagnosticController(state, self.stats, self.publisher).handle(IDENTIFICATION, diagnostic_message())
        state.update_identification.assert_called_once_with(IDENTIFICATION, COMPLETED_AT_NS)

    def test_incomplete_or_invalid_results_are_rejected(self) -> None:
        self.controller.handle(IDENTIFICATION, diagnostic_message())
        other_module = DiagnosticResult(DIAGNOSTIC_BASE_ID + 1, MODULE_COUNT, "SN:X FW:1", "X", "1")
        empty_text = DiagnosticResult(DIAGNOSTIC_BASE_ID + 1, 1, "", "", "")
        cases = [
            (IDENTIFICATION, diagnostic_message(completed_at_ns=None)),
            (IDENTIFICATION, diagnostic_message(can_id=DIAGNOSTIC_BASE_ID + 2)),
            (other_module, diagnostic_message()),
            (empty_text, diagnostic_message()),
        ]
        for result, message in cases:
            outcome = self.controller.handle(result, message)
            self.assertIs(outcome.status, ControllerStatus.REJECTED, outcome)
            self.assertTrue(outcome.reason)
        self.assertIs(self.state.identification(1), IDENTIFICATION)
        self.assertEqual(len(self.publisher.events), 1)
        self.assert_counts(EventType.DIAG_COMPLETE, 1, len(cases))

    def test_invalid_result_does_not_block_the_next_valid_one(self) -> None:
        self.controller.handle(IDENTIFICATION, diagnostic_message(completed_at_ns=None))
        self.assertTrue(self.controller.handle(IDENTIFICATION, diagnostic_message()).succeeded)
        self.assertEqual(len(self.publisher.events), 1)

    def test_state_failure_propagates_without_publishing_or_counting(self) -> None:
        with mock.patch.object(self.state, "update_identification", side_effect=RuntimeError("state broken")):
            with self.assertRaises(RuntimeError):
                self.controller.handle(IDENTIFICATION, diagnostic_message())
        self.assertEqual(self.publisher.events, [])
        self.assert_counts(EventType.DIAG_COMPLETE, 0, 0)


if __name__ == "__main__":
    unittest.main()
