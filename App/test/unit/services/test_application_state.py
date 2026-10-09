"""Unit tests for ApplicationState."""

import dataclasses
import tracemalloc
import unittest

from config.constants import DIAGNOSTIC_BASE_ID, MODULE_COUNT
from models.application_event import DiagnosticCompleteEvent
from protocol.diagnostic import DiagnosticResult
from protocol.fault import FaultCode, FaultResult
from protocol.telemetry import TelemetryResult
from services.application_state import ApplicationState, StateSnapshot

COMPLETED_AT_NS = 88_123_456_789


def telemetry(module_id: int, sequence: int) -> TelemetryResult:
    """Build a telemetry result for ``module_id``."""
    return TelemetryResult(module_id, sequence, 400.0, 100.0, 45, True, False, False)


def identification(module_id: int, text: str) -> DiagnosticResult:
    """Build an identification result for ``module_id``."""
    return DiagnosticResult(DIAGNOSTIC_BASE_ID + module_id, module_id, text, "X", "1")


class ApplicationStateTest(unittest.TestCase):
    """Latest values per module and a bounded fault history."""

    def setUp(self) -> None:
        self.state = ApplicationState(recent_fault_limit=3)

    def test_starts_empty(self) -> None:
        self.assertEqual(self.state.module_count, MODULE_COUNT)
        for module_id in range(MODULE_COUNT):
            self.assertIsNone(self.state.telemetry(module_id))
            self.assertIsNone(self.state.latest_fault(module_id))
            self.assertIsNone(self.state.identification(module_id))
            self.assertIsNone(self.state.diagnostic_completion(module_id))
        self.assertEqual(self.state.recent_faults, ())

    def test_keeps_only_the_latest_telemetry_per_module(self) -> None:
        self.state.update_telemetry(telemetry(1, 10))
        self.state.update_telemetry(telemetry(1, 11))
        self.state.update_telemetry(telemetry(2, 5))
        self.assertEqual(self.state.telemetry(1).sequence, 11)
        self.assertEqual(self.state.telemetry(2).sequence, 5)
        self.assertIsNone(self.state.telemetry(0))

    def test_keeps_the_latest_identification_with_its_completion_timestamp(self) -> None:
        self.state.update_identification(identification(3, "SN:A FW:1 #1"), 10)
        self.state.update_identification(identification(3, "SN:A FW:1 #2"), COMPLETED_AT_NS)
        self.assertEqual(self.state.identification(3).text, "SN:A FW:1 #2")
        self.assertEqual(
            self.state.diagnostic_completion(3),
            DiagnosticCompleteEvent(identification(3, "SN:A FW:1 #2"), COMPLETED_AT_NS),
        )
        self.assertIsNone(self.state.identification(0))

    def test_tracks_the_current_fault_per_module(self) -> None:
        self.state.record_fault(FaultResult(2, FaultCode.OVERTEMP))
        self.state.record_fault(FaultResult(2, FaultCode.UNDERVOLTAGE))
        self.state.record_fault(FaultResult(0, FaultCode.OVERVOLTAGE))
        self.assertEqual(self.state.latest_fault(2), FaultResult(2, FaultCode.UNDERVOLTAGE))
        self.assertEqual(self.state.latest_fault(0), FaultResult(0, FaultCode.OVERVOLTAGE))
        self.assertIsNone(self.state.latest_fault(1))

    def test_fault_history_is_bounded_and_drops_the_oldest(self) -> None:
        faults = [FaultResult(module_id % MODULE_COUNT, FaultCode.OVERTEMP) for module_id in range(10)]
        for fault in faults:
            self.state.record_fault(fault)
        self.assertEqual(self.state.recent_faults, tuple(faults[-3:]))

    def test_rejects_invalid_sizes(self) -> None:
        with self.assertRaises(ValueError):
            ApplicationState(module_count=0)
        with self.assertRaises(ValueError):
            ApplicationState(recent_fault_limit=0)


class InvalidUpdateTest(unittest.TestCase):
    """An invalid update raises and leaves the last valid state untouched."""

    def setUp(self) -> None:
        self.state = ApplicationState()
        self.state.update_telemetry(telemetry(1, 7))
        self.state.record_fault(FaultResult(1, FaultCode.OVERTEMP))
        self.state.update_identification(identification(1, "SN:A FW:1"), COMPLETED_AT_NS)
        self.before = self.state.snapshot()

    def assert_unchanged(self) -> None:
        self.assertEqual(self.state.snapshot(), self.before)

    def test_invalid_telemetry_keeps_the_last_valid_telemetry(self) -> None:
        for bad in (telemetry(MODULE_COUNT, 8), telemetry(-1, 8), dataclasses.replace(telemetry(0, 8), module_id=True)):
            with self.subTest(bad=bad), self.assertRaises((ValueError, TypeError)):
                self.state.update_telemetry(bad)
        with self.assertRaises(TypeError):
            self.state.update_telemetry(FaultResult(1, FaultCode.OVERTEMP))  # type: ignore[arg-type]
        self.assert_unchanged()

    def test_invalid_fault_keeps_the_last_valid_fault(self) -> None:
        for bad in (FaultResult(MODULE_COUNT, FaultCode.OVERTEMP), FaultResult(1, 9)):  # type: ignore[arg-type]
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.state.record_fault(bad)
        self.assert_unchanged()

    def test_invalid_identification_keeps_the_last_valid_completion(self) -> None:
        cases = [
            (identification(1, ""), COMPLETED_AT_NS),
            (dataclasses.replace(identification(1, "SN:B FW:2"), message_id=DIAGNOSTIC_BASE_ID), COMPLETED_AT_NS),
            (identification(MODULE_COUNT, "SN:B FW:2"), COMPLETED_AT_NS),
            (identification(1, "SN:B FW:2"), -1),
            (identification(1, "SN:B FW:2"), None),
            (identification(1, "SN:B FW:2"), True),
        ]
        for result, completed_at_ns in cases:
            with self.subTest(result=result, completed_at_ns=completed_at_ns), self.assertRaises(ValueError):
                self.state.update_identification(result, completed_at_ns)  # type: ignore[arg-type]
        self.assert_unchanged()


class SnapshotTest(unittest.TestCase):
    """Snapshots are immutable copies."""

    def setUp(self) -> None:
        self.state = ApplicationState(recent_fault_limit=2)
        self.state.update_telemetry(telemetry(0, 1))
        self.state.record_fault(FaultResult(3, FaultCode.ISOLATION_FAULT))
        self.state.update_identification(identification(2, "SN:C FW:3"), COMPLETED_AT_NS)

    def test_snapshot_reflects_the_state(self) -> None:
        snapshot = self.state.snapshot()
        self.assertIsInstance(snapshot, StateSnapshot)
        self.assertEqual(snapshot.module_count, MODULE_COUNT)
        self.assertEqual(snapshot.telemetry, (telemetry(0, 1), None, None, None))
        self.assertEqual(snapshot.latest_faults, (None, None, None, FaultResult(3, FaultCode.ISOLATION_FAULT)))
        self.assertEqual(snapshot.diagnostic_completions[2].completed_at_ns, COMPLETED_AT_NS)
        self.assertEqual(snapshot.recent_faults, (FaultResult(3, FaultCode.ISOLATION_FAULT),))

    def test_snapshot_cannot_mutate_the_state(self) -> None:
        snapshot = self.state.snapshot()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            snapshot.telemetry = ()  # type: ignore[misc]
        with self.assertRaises(TypeError):
            snapshot.telemetry[0] = None  # type: ignore[index]
        with self.assertRaises(dataclasses.FrozenInstanceError):
            snapshot.telemetry[0].sequence = 99  # type: ignore[misc,union-attr]
        self.assertEqual(self.state.telemetry(0), telemetry(0, 1))

    def test_snapshot_does_not_follow_later_updates(self) -> None:
        snapshot = self.state.snapshot()
        self.state.update_telemetry(telemetry(0, 2))
        self.state.record_fault(FaultResult(0, FaultCode.OVERTEMP))
        self.assertEqual(snapshot.telemetry[0].sequence, 1)
        self.assertEqual(len(snapshot.recent_faults), 1)

    def test_recent_faults_is_a_copy(self) -> None:
        self.assertIsInstance(self.state.recent_faults, tuple)
        self.assertIsNot(self.state.recent_faults, self.state.recent_faults)


class BoundedMemoryTest(unittest.TestCase):
    """State size does not grow with the amount of traffic."""

    def test_memory_stays_bounded_over_extended_processing(self) -> None:
        state = ApplicationState(recent_fault_limit=5)

        def process(rounds: int) -> None:
            for index in range(rounds):
                module_id = index % MODULE_COUNT
                state.update_telemetry(telemetry(module_id, index))
                state.record_fault(FaultResult(module_id, FaultCode.OVERTEMP))
                state.update_identification(identification(module_id, f"SN:A FW:1 #{index}"), index)

        process(1_000)
        tracemalloc.start()
        try:
            process(1_000)
            baseline, _ = tracemalloc.get_traced_memory()
            process(20_000)
            after, _ = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertLess(after - baseline, 16 * 1024)
        self.assertEqual(len(state.recent_faults), 5)


if __name__ == "__main__":
    unittest.main()
