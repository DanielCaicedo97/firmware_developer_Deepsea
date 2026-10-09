"""Unit tests for SubRouter registration and dispatch."""

import unittest
from typing import List

from config.constants import CAN_STANDARD_ID_MASK
from helpers import complete_message
from models.message import Message
from routes.common import DispatchStatus, RouteRegistrationError, SubRouter


class ExpectedError(ValueError):
    """Stands in for a decoder's validation error."""


class RecordingHandler:
    """Handler double that records each message and returns a fixed result."""

    def __init__(self, result: object = "handled") -> None:
        self.result = result
        self.messages: List[Message] = []

    def __call__(self, message: Message) -> object:
        self.messages.append(message)
        return self.result


class SubRouterRegistrationTest(unittest.TestCase):
    """Registration validates IDs and handlers and never overwrites."""

    def setUp(self) -> None:
        self.router = SubRouter("test")

    def test_add_route_and_add_routes(self) -> None:
        self.router.add_route(0x10, RecordingHandler())
        self.router.add_routes([0x20, 0x21], RecordingHandler())
        self.assertEqual(self.router.can_ids, (0x10, 0x20, 0x21))
        self.assertTrue(self.router.handles(0x21))
        self.assertFalse(self.router.handles(0x22))

    def test_decorator_registers_and_returns_the_handler(self) -> None:
        @self.router.route(0x30, 0x31)
        def handler(message: Message) -> str:
            return "decorated"

        self.assertEqual(self.router.can_ids, (0x30, 0x31))
        self.assertEqual(handler(complete_message(0x30, b"")), "decorated")

    def test_duplicate_route_is_rejected_and_original_kept(self) -> None:
        original = RecordingHandler("original")
        self.router.add_route(0x10, original)
        with self.assertRaises(RouteRegistrationError):
            self.router.add_route(0x10, RecordingHandler("replacement"))
        self.assertEqual(self.router.dispatch(complete_message(0x10, b"")).result, "original")

    def test_duplicate_ids_within_one_registration_are_rejected(self) -> None:
        with self.assertRaises(RouteRegistrationError):
            self.router.add_routes([0x10, 0x10], RecordingHandler())
        self.assertEqual(self.router.can_ids, ())

    def test_conflicting_batch_registers_nothing(self) -> None:
        self.router.add_route(0x11, RecordingHandler())
        with self.assertRaises(RouteRegistrationError):
            self.router.add_routes([0x10, 0x11, 0x12], RecordingHandler())
        self.assertEqual(self.router.can_ids, (0x11,))

    def test_invalid_identifiers_are_rejected(self) -> None:
        for can_id in (-1, CAN_STANDARD_ID_MASK + 1, 0x80000100, "0x100", 1.0, None, True):
            with self.subTest(can_id=can_id), self.assertRaises(RouteRegistrationError):
                self.router.add_route(can_id, RecordingHandler())
        self.assertEqual(self.router.can_ids, ())

    def test_boundary_identifiers_are_accepted(self) -> None:
        self.router.add_routes([0, CAN_STANDARD_ID_MASK], RecordingHandler())
        self.assertEqual(self.router.can_ids, (0, CAN_STANDARD_ID_MASK))

    def test_empty_registration_is_rejected(self) -> None:
        with self.assertRaises(RouteRegistrationError):
            self.router.add_routes([], RecordingHandler())

    def test_non_callable_handlers_are_rejected(self) -> None:
        for handler in (None, "decode", 42, object()):
            with self.subTest(handler=handler), self.assertRaises(RouteRegistrationError):
                self.router.add_route(0x10, handler)
        self.assertEqual(self.router.can_ids, ())

    def test_invalid_names_are_rejected(self) -> None:
        for name in ("", None, 3):
            with self.subTest(name=name), self.assertRaises(RouteRegistrationError):
                SubRouter(name)

    def test_instances_keep_independent_registrations(self) -> None:
        other = SubRouter("other")
        self.router.add_route(0x10, RecordingHandler())
        other.add_route(0x10, RecordingHandler())
        other.add_route(0x11, RecordingHandler())
        self.assertEqual(self.router.can_ids, (0x10,))
        self.assertEqual(other.can_ids, (0x10, 0x11))


class SubRouterDispatchTest(unittest.TestCase):
    """Dispatch invokes the right handler and reports every outcome."""

    def setUp(self) -> None:
        self.first = RecordingHandler("first-result")
        self.second = RecordingHandler("second-result")
        self.router = SubRouter("test", expected_errors=(ExpectedError,))
        self.router.add_route(0x10, self.first)
        self.router.add_route(0x11, self.second)

    def test_invokes_the_handler_for_the_id_with_the_original_message(self) -> None:
        message = complete_message(0x11, b"\x01\x02")
        self.router.dispatch(message)
        self.assertEqual(self.first.messages, [])
        self.assertEqual(len(self.second.messages), 1)
        self.assertIs(self.second.messages[0], message)

    def test_success_returns_the_handlers_result(self) -> None:
        message = complete_message(0x10, b"")
        dispatched = self.router.dispatch(message)
        self.assertIs(dispatched.status, DispatchStatus.SUCCESS)
        self.assertTrue(dispatched.succeeded)
        self.assertEqual(dispatched.result, "first-result")
        self.assertEqual(dispatched.router_name, "test")
        self.assertIs(dispatched.message, message)
        self.assertIsNone(dispatched.error)

    def test_missing_handler_is_reported(self) -> None:
        dispatched = self.router.dispatch(complete_message(0x12, b""))
        self.assertIs(dispatched.status, DispatchStatus.HANDLER_NOT_FOUND)
        self.assertFalse(dispatched.succeeded)
        self.assertEqual(dispatched.router_name, "test")
        self.assertIsNone(dispatched.result)

    def test_expected_handler_error_becomes_handler_failed(self) -> None:
        error = ExpectedError("malformed")

        def failing(message: Message) -> None:
            raise error

        self.router.add_route(0x12, failing)
        dispatched = self.router.dispatch(complete_message(0x12, b""))
        self.assertIs(dispatched.status, DispatchStatus.HANDLER_FAILED)
        self.assertIs(dispatched.error, error)
        self.assertIsNone(dispatched.result)
        # The router keeps working after a failure.
        self.assertTrue(self.router.dispatch(complete_message(0x10, b"")).succeeded)

    def test_unexpected_errors_propagate(self) -> None:
        def broken(message: Message) -> None:
            raise RuntimeError("bug")

        self.router.add_route(0x12, broken)
        with self.assertRaises(RuntimeError):
            self.router.dispatch(complete_message(0x12, b""))

    def test_without_expected_errors_nothing_is_caught(self) -> None:
        router = SubRouter("strict")

        def failing(message: Message) -> None:
            raise ExpectedError("malformed")

        router.add_route(0x10, failing)
        with self.assertRaises(ExpectedError):
            router.dispatch(complete_message(0x10, b""))


if __name__ == "__main__":
    unittest.main()
