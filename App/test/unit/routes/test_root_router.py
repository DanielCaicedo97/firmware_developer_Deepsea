"""Unit tests for RootRouter inclusion and delegation."""

import unittest
from typing import List

from helpers import complete_message
from models.message import Message
from routes.common import DispatchStatus, RootRouter, RouteRegistrationError, SubRouter


class RecordingHandler:
    """Handler double that records each message and returns a fixed result."""

    def __init__(self, result: object) -> None:
        self.result = result
        self.messages: List[Message] = []

    def __call__(self, message: Message) -> object:
        self.messages.append(message)
        return self.result


def subrouter_with(name: str, *can_ids: int) -> SubRouter:
    """Build a subrouter whose handler returns ``"<name>-result"``."""
    subrouter = SubRouter(name)
    subrouter.add_routes(can_ids, RecordingHandler(f"{name}-result"))
    return subrouter


class RootRouterIncludeTest(unittest.TestCase):
    """Including subrouters indexes their IDs and rejects conflicts."""

    def setUp(self) -> None:
        self.root = RootRouter()

    def test_include_indexes_the_subrouters_ids(self) -> None:
        self.root.include_router(subrouter_with("a", 0x10, 0x11))
        self.root.include_router(subrouter_with("b", 0x20))
        self.assertEqual(self.root.can_ids, (0x10, 0x11, 0x20))
        self.assertEqual(self.root.name, "root")

    def test_overlapping_subrouters_are_rejected_all_or_none(self) -> None:
        self.root.include_router(subrouter_with("a", 0x10))
        with self.assertRaises(RouteRegistrationError):
            self.root.include_router(subrouter_with("b", 0x20, 0x10))
        self.assertEqual(self.root.can_ids, (0x10,))
        self.assertEqual(self.root.dispatch(complete_message(0x10, b"")).router_name, "a")

    def test_including_the_same_subrouter_twice_is_rejected(self) -> None:
        subrouter = subrouter_with("a", 0x10)
        self.root.include_router(subrouter)
        with self.assertRaises(RouteRegistrationError):
            self.root.include_router(subrouter)

    def test_empty_subrouter_is_rejected(self) -> None:
        with self.assertRaises(RouteRegistrationError):
            self.root.include_router(SubRouter("empty"))

    def test_non_subrouter_is_rejected(self) -> None:
        for candidate in (None, RecordingHandler("x"), RootRouter("other")):
            with self.subTest(candidate=candidate), self.assertRaises(RouteRegistrationError):
                self.root.include_router(candidate)

    def test_instances_keep_independent_registrations(self) -> None:
        other = RootRouter()
        self.root.include_router(subrouter_with("a", 0x10))
        other.include_router(subrouter_with("a", 0x10))
        other.include_router(subrouter_with("b", 0x20))
        self.assertEqual(self.root.can_ids, (0x10,))
        self.assertEqual(other.can_ids, (0x10, 0x20))
        self.assertIs(self.root.dispatch(complete_message(0x20, b"")).status, DispatchStatus.ROUTE_NOT_FOUND)


class RootRouterDispatchTest(unittest.TestCase):
    """Dispatch reaches the right subrouter, or reports where routing stopped."""

    def setUp(self) -> None:
        self.handler_a = RecordingHandler("a-result")
        self.handler_b = RecordingHandler("b-result")
        self.sub_a = SubRouter("a")
        self.sub_a.add_routes([0x10, 0x11], self.handler_a)
        self.sub_b = SubRouter("b")
        self.sub_b.add_route(0x20, self.handler_b)
        self.root = RootRouter()
        self.root.include_router(self.sub_a)
        self.root.include_router(self.sub_b)

    def test_message_reaches_the_correct_subrouter_and_handler(self) -> None:
        message = complete_message(0x20, b"\xaa")
        dispatched = self.root.dispatch(message)
        self.assertEqual(dispatched.router_name, "b")
        self.assertEqual(self.handler_a.messages, [])
        self.assertIs(self.handler_b.messages[0], message)

    def test_success_returns_the_handlers_result(self) -> None:
        message = complete_message(0x11, b"")
        dispatched = self.root.dispatch(message)
        self.assertIs(dispatched.status, DispatchStatus.SUCCESS)
        self.assertEqual(dispatched.result, "a-result")
        self.assertIs(dispatched.message, message)

    def test_missing_root_route_is_route_not_found(self) -> None:
        message = complete_message(0x30, b"")
        dispatched = self.root.dispatch(message)
        self.assertIs(dispatched.status, DispatchStatus.ROUTE_NOT_FOUND)
        self.assertIsNone(dispatched.router_name)
        self.assertIsNone(dispatched.result)
        self.assertIsNone(dispatched.error)
        self.assertIs(dispatched.message, message)
        self.assertEqual(self.handler_a.messages + self.handler_b.messages, [])

    def test_registration_after_inclusion_is_rejected(self) -> None:
        self.assertTrue(self.sub_b.sealed)
        with self.assertRaises(RouteRegistrationError):
            self.sub_b.add_route(0x21, self.handler_b)
        self.assertEqual(self.sub_b.can_ids, (0x20,))

    def test_missing_subroute_is_handler_not_found(self) -> None:
        # The root only indexes IDs its subrouters registered, so a missing
        # handler is reported by the subrouter when it is dispatched directly.
        dispatched = self.sub_a.dispatch(complete_message(0x12, b""))
        self.assertIs(dispatched.status, DispatchStatus.HANDLER_NOT_FOUND)
        self.assertEqual(dispatched.router_name, "a")
        self.assertEqual(self.handler_a.messages, [])


if __name__ == "__main__":
    unittest.main()
