"""Unit tests for EventPublisher and its consumer failure policy."""

import unittest

from helpers import RecordingConsumer
from models.application_event import ApplicationEvent, DiagnosticCompleteEvent, FaultEvent, StatsEvent, TelemetryEvent
from protocol.diagnostic import DiagnosticResult
from protocol.fault import FaultCode, FaultResult
from protocol.telemetry import TelemetryResult
from services.event_publisher import EventConsumer, EventDeliveryError, EventPublisher

COMPLETED_AT_NS = 88_123_456_789
EVENTS = [
    TelemetryEvent(TelemetryResult(0, 4821, 412.3, 118.55, 47, True, False, False)),
    FaultEvent(FaultResult(2, FaultCode.OVERTEMP)),
    DiagnosticCompleteEvent(DiagnosticResult(0x6F0, 0, "SN:PMU-4471-A FW:2.3.1", "PMU-4471-A", "2.3.1"),
                            completed_at_ns=COMPLETED_AT_NS),
    StatsEvent(frames_processed=15234),
]


class FailingConsumer(EventConsumer):
    """Consumer double that raises on every event."""

    def __init__(self, error: BaseException) -> None:
        self.error = error
        self.calls = 0

    def on_event(self, event: ApplicationEvent) -> None:
        """Count the call, then raise."""
        self.calls += 1
        raise self.error


class EventPublisherTest(unittest.TestCase):
    """Registration and synchronous delivery."""

    def setUp(self) -> None:
        self.publisher = EventPublisher()

    def test_registered_consumers_receive_every_event_in_order(self) -> None:
        first, second = RecordingConsumer(), RecordingConsumer()
        self.publisher.register(first)
        self.publisher.register(second)
        for event in EVENTS:
            self.publisher.publish(event)
        self.assertEqual(first.events, EVENTS)
        self.assertEqual(second.events, EVENTS)
        self.assertEqual(self.publisher.consumers, (first, second))

    def test_events_are_delivered_unchanged_with_their_timestamp(self) -> None:
        consumer = RecordingConsumer()
        self.publisher.register(consumer)
        self.publisher.publish(EVENTS[2])
        self.assertIs(consumer.events[0], EVENTS[2])
        self.assertEqual(consumer.events[0].completed_at_ns, COMPLETED_AT_NS)
        self.assertEqual(consumer.events[0].diagnostic.message_id, 0x6F0)

    def test_publishing_without_consumers_is_a_no_op(self) -> None:
        self.publisher.publish(EVENTS[0])
        self.assertEqual(self.publisher.consumers, ())

    def test_a_consumer_cannot_be_registered_twice(self) -> None:
        consumer = RecordingConsumer()
        self.publisher.register(consumer)
        with self.assertRaises(ValueError):
            self.publisher.register(consumer)
        self.publisher.publish(EVENTS[0])
        self.assertEqual(consumer.events, [EVENTS[0]])

    def test_only_event_consumers_can_be_registered(self) -> None:
        with self.assertRaises(TypeError):
            self.publisher.register(object())  # type: ignore[arg-type]
        self.assertEqual(self.publisher.consumers, ())

    def test_consumers_tuple_does_not_expose_the_registry(self) -> None:
        self.publisher.register(RecordingConsumer())
        consumers = self.publisher.consumers
        self.assertIsInstance(consumers, tuple)
        self.assertEqual(len(self.publisher.consumers), 1)


class ConsumerFailurePolicyTest(unittest.TestCase):
    """A failing consumer is logged, the others still receive the event, and the caller gets an error."""

    def setUp(self) -> None:
        self.publisher = EventPublisher()
        self.before, self.after = RecordingConsumer(), RecordingConsumer()
        self.failing = FailingConsumer(OSError("stdout closed"))
        for consumer in (self.before, self.failing, self.after):
            self.publisher.register(consumer)

    def test_other_consumers_still_receive_the_event(self) -> None:
        with self.assertLogs("services.event_publisher", "ERROR"), self.assertRaises(EventDeliveryError):
            self.publisher.publish(EVENTS[3])
        self.assertEqual(self.before.events, [EVENTS[3]])
        self.assertEqual(self.after.events, [EVENTS[3]])

    def test_the_failure_is_raised_after_delivery_and_never_silent(self) -> None:
        with self.assertLogs("services.event_publisher", "ERROR") as logs, \
                self.assertRaises(EventDeliveryError) as raised:
            self.publisher.publish(EVENTS[1])
        self.assertEqual(raised.exception.failures, ((self.failing, self.failing.error),))
        self.assertIs(raised.exception.__cause__, self.failing.error)
        self.assertIs(raised.exception.event, EVENTS[1])
        self.assertIn("FailingConsumer", logs.output[0])

    def test_later_events_are_still_delivered(self) -> None:
        for event in EVENTS[:2]:
            with self.assertLogs("services.event_publisher", "ERROR"), self.assertRaises(EventDeliveryError):
                self.publisher.publish(event)
        self.assertEqual(self.after.events, EVENTS[:2])
        self.assertEqual(self.failing.calls, 2)

    def test_every_failure_is_reported(self) -> None:
        second_failing = FailingConsumer(ValueError("bad value"))
        self.publisher.register(second_failing)
        with self.assertLogs("services.event_publisher", "ERROR") as logs, \
                self.assertRaises(EventDeliveryError) as raised:
            self.publisher.publish(EVENTS[0])
        self.assertEqual([consumer for consumer, _ in raised.exception.failures], [self.failing, second_failing])
        self.assertEqual(len(logs.output), 2)

    def test_keyboard_interrupt_is_not_caught(self) -> None:
        publisher = EventPublisher()
        publisher.register(FailingConsumer(KeyboardInterrupt()))
        with self.assertRaises(KeyboardInterrupt):
            publisher.publish(EVENTS[0])


if __name__ == "__main__":
    unittest.main()
