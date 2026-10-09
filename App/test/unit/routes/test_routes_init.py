"""Unit tests for the domain routes and their composition in ``init_routes``."""

import contextlib
import io
import struct
import unittest
from typing import List

from config.constants import (
    DIAGNOSTIC_BASE_ID,
    FAULT_ID,
    MODULE_COUNT,
    NOISE_ID_FIRST,
    NOISE_ID_LAST,
    TELEMETRY_BASE_ID,
)
from helpers import RecordingController, complete_message
from models.message import FramingMode, Message
from protocol.common import ProtocolDecodeError
from protocol.fault import FaultCode, FaultResult
from protocol.telemetry import TelemetryResult
from routes.common import DispatchStatus, RootRouter, RouteRegistrationError, SubRouter
from routes.diagnostic import build_diagnostic_router
from routes.fault import build_fault_router
from routes.routes_init import init_routes
from routes.telemetry import build_telemetry_router

TELEMETRY_IDS = tuple(range(TELEMETRY_BASE_ID, TELEMETRY_BASE_ID + MODULE_COUNT))
DIAGNOSTIC_IDS = tuple(range(DIAGNOSTIC_BASE_ID, DIAGNOSTIC_BASE_ID + MODULE_COUNT))
NOISE_IDS = tuple(range(NOISE_ID_FIRST, NOISE_ID_LAST + 1))
UNKNOWN_IDS = (0x000, TELEMETRY_BASE_ID - 1, TELEMETRY_BASE_ID + MODULE_COUNT, FAULT_ID - 1, FAULT_ID + 1,
               DIAGNOSTIC_BASE_ID - 1, DIAGNOSTIC_BASE_ID + MODULE_COUNT, 0x7FF)


class RecordingDecoder:
    """Decoder double that records each message and returns a fixed result."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.messages: List[Message] = []

    def __call__(self, message: Message) -> str:
        self.messages.append(message)
        return f"{self.name}-result"


def build_controllers() -> List[RecordingController]:
    """Return fresh telemetry, fault and diagnostic controller doubles."""
    return [RecordingController(), RecordingController(), RecordingController()]


class RouteInitializationTest(unittest.TestCase):
    """init_routes registers every documented challenge route and nothing else."""

    def test_registers_all_documented_ids(self) -> None:
        root = init_routes(*build_controllers())
        self.assertEqual(root.can_ids, tuple(sorted(TELEMETRY_IDS + (FAULT_ID,) + DIAGNOSTIC_IDS)))

    def test_uses_a_supplied_root_and_returns_it(self) -> None:
        root = RootRouter()
        self.assertIs(init_routes(*build_controllers(), root=root), root)
        self.assertEqual(len(root.can_ids), 2 * MODULE_COUNT + 1)

    def test_each_call_builds_independent_routers(self) -> None:
        first, second = init_routes(*build_controllers()), init_routes(*build_controllers())
        self.assertIsNot(first, second)
        extra = SubRouter("extra")
        extra.add_route(0x7FF, RecordingDecoder("extra"))
        second.include_router(extra)
        self.assertFalse(first.handles(0x7FF))
        self.assertTrue(second.handles(0x7FF))

    def test_rejects_a_root_that_already_owns_a_challenge_id(self) -> None:
        root = RootRouter()
        clash = SubRouter("clash")
        clash.add_route(FAULT_ID, RecordingDecoder("clash"))
        root.include_router(clash)
        with self.assertRaises(RouteRegistrationError):
            init_routes(*build_controllers(), root=root)


class DomainRouteTest(unittest.TestCase):
    """Each domain router sends its IDs through its decoder to its controller."""

    def setUp(self) -> None:
        self.decoders = [RecordingDecoder("telemetry"), RecordingDecoder("fault"), RecordingDecoder("diagnostic")]
        self.controllers = build_controllers()
        builders = (build_telemetry_router, build_fault_router, build_diagnostic_router)
        self.root = RootRouter()
        for builder, controller, decoder in zip(builders, self.controllers, self.decoders):
            self.root.include_router(builder(controller, decoder))

    def call_counts(self) -> List[int]:
        return [len(controller.handled) for controller in self.controllers]

    def test_all_telemetry_ids_reach_the_telemetry_controller(self) -> None:
        for can_id in TELEMETRY_IDS:
            message = complete_message(can_id, bytes(8))
            dispatched = self.root.dispatch(message)
            self.assertEqual((dispatched.router_name, dispatched.result.decoded), ("telemetry", "telemetry-result"))
            self.assertEqual(self.controllers[0].handled[-1], ("telemetry-result", message))
        self.assertEqual(self.call_counts(), [MODULE_COUNT, 0, 0])

    def test_fault_id_reaches_the_fault_controller(self) -> None:
        message = complete_message(FAULT_ID, bytes(8))
        dispatched = self.root.dispatch(message)
        self.assertEqual((dispatched.router_name, dispatched.result.decoded), ("fault", "fault-result"))
        self.assertEqual(self.controllers[1].handled, [("fault-result", message)])
        self.assertEqual(self.call_counts(), [0, 1, 0])

    def test_all_diagnostic_ids_reach_the_diagnostic_controller(self) -> None:
        for can_id in DIAGNOSTIC_IDS:
            message = complete_message(can_id, b"SN:X FW:1", FramingMode.SEGMENTED)
            dispatched = self.root.dispatch(message)
            self.assertEqual((dispatched.router_name, dispatched.result.decoded), ("diagnostic", "diagnostic-result"))
            self.assertIs(self.controllers[2].handled[-1][1], message)
        self.assertEqual(self.call_counts(), [0, 0, MODULE_COUNT])

    def test_noise_and_unknown_ids_never_reach_a_decoder_or_controller(self) -> None:
        for can_id in NOISE_IDS + UNKNOWN_IDS:
            dispatched = self.root.dispatch(complete_message(can_id, bytes(8)))
            self.assertIs(dispatched.status, DispatchStatus.ROUTE_NOT_FOUND)
        self.assertEqual([len(decoder.messages) for decoder in self.decoders], [0, 0, 0])
        self.assertEqual(self.call_counts(), [0, 0, 0])

    def test_payload_reaches_the_decoder_untouched(self) -> None:
        # A First-Frame-looking payload: routes neither parse nor reassemble it.
        payload = bytes([0x10, 0x14]) + b"\xff\x00garbage"
        message = complete_message(DIAGNOSTIC_BASE_ID, payload, FramingMode.SEGMENTED)
        self.root.dispatch(message)
        self.assertIs(self.decoders[2].messages[0].payload, payload)


class RealDecoderRoutingTest(unittest.TestCase):
    """The default routes use the protocol decoders before the controllers."""

    def setUp(self) -> None:
        self.controllers = build_controllers()
        self.root = init_routes(*self.controllers)

    def test_valid_telemetry_reaches_the_controller_decoded(self) -> None:
        payload = struct.pack("<HHBBH", 4123, 11855, 87, 0x01, 4821)
        dispatched = self.root.dispatch(complete_message(TELEMETRY_BASE_ID + 2, payload))
        self.assertIs(dispatched.status, DispatchStatus.SUCCESS)
        telemetry = dispatched.result.decoded
        self.assertIsInstance(telemetry, TelemetryResult)
        self.assertEqual((telemetry.module_id, telemetry.sequence), (2, 4821))
        self.assertIs(self.controllers[0].handled[0][0], telemetry)

    def test_malformed_messages_never_reach_a_controller_and_routing_continues(self) -> None:
        malformed = [
            complete_message(TELEMETRY_BASE_ID, bytes(3)),
            complete_message(FAULT_ID, bytes([0, 9, 0, 0, 0, 0, 0, 0])),
            complete_message(DIAGNOSTIC_BASE_ID, b"\x01\x02\x03\x04\x05\x06\x07\x08", FramingMode.SEGMENTED),
        ]
        for message in malformed:
            dispatched = self.root.dispatch(message)
            self.assertIs(dispatched.status, DispatchStatus.HANDLER_FAILED)
            self.assertIsInstance(dispatched.error, ProtocolDecodeError)
            self.assertIsNone(dispatched.result)
        self.assertEqual([len(controller.handled) for controller in self.controllers], [0, 0, 0])
        valid = self.root.dispatch(complete_message(FAULT_ID, bytes([1, 4, 0, 0, 0, 0, 0, 0])))
        self.assertEqual(valid.result.decoded, FaultResult(module_id=1, code=FaultCode.ISOLATION_FAULT))
        self.assertEqual(len(self.controllers[1].handled), 1)

    def test_routing_writes_nothing_to_stdout(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            self.root.dispatch(complete_message(FAULT_ID, bytes([0, 1, 0, 0, 0, 0, 0, 0])))
            self.root.dispatch(complete_message(FAULT_ID, bytes(2)))
            self.root.dispatch(complete_message(NOISE_ID_FIRST, bytes(8)))
        self.assertEqual(stdout.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
