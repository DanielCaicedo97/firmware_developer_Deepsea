"""Application event publication: one publisher, any number of registered consumers.

Delivery is synchronous, in registration order, with no queue or thread.

Consumer failure policy: every registered consumer receives every event. If a
consumer raises an ``Exception``, the failure is logged on stderr and delivery
continues with the remaining consumers. Once all consumers have been called,
``EventDeliveryError`` is raised so the failure reaches the caller and is
never silent. ``BaseException`` (``KeyboardInterrupt``, ``SystemExit``) is not
caught.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import List, Sequence, Tuple

from models.application_event import ApplicationEvent

logger = logging.getLogger(__name__)


class EventConsumer(ABC):
    """Receives application events from an ``EventPublisher`` (an output mode)."""

    @abstractmethod
    def on_event(self, event: ApplicationEvent) -> None:
        """Handle one application event."""


class EventDeliveryError(RuntimeError):
    """One or more consumers failed while an event was delivered to all of them.

    ``failures`` pairs each failing consumer with its exception, in delivery
    order; the first exception is also chained as ``__cause__``.
    """

    def __init__(self, event: ApplicationEvent, failures: Sequence[Tuple[EventConsumer, Exception]]) -> None:
        names = ", ".join(type(consumer).__name__ for consumer, _ in failures)
        super().__init__(f"{event.event_type.value} event delivery failed in: {names}")
        self.event = event
        self.failures: Tuple[Tuple[EventConsumer, Exception], ...] = tuple(failures)


class EventPublisher:
    """Delivers each published event, unchanged, to every registered consumer.

    Controllers depend only on ``publish``; the composition root registers the
    output consumer of the selected mode.
    """

    def __init__(self) -> None:
        self._consumers: List[EventConsumer] = []

    @property
    def consumers(self) -> Tuple[EventConsumer, ...]:
        """The registered consumers, in delivery order."""
        return tuple(self._consumers)

    def register(self, consumer: EventConsumer) -> None:
        """Add ``consumer``; registering the same consumer twice is an error."""
        if not isinstance(consumer, EventConsumer):
            raise TypeError(f"not an EventConsumer: {consumer!r}")
        if consumer in self._consumers:
            raise ValueError(f"consumer already registered: {consumer!r}")
        self._consumers.append(consumer)

    def publish(self, event: ApplicationEvent) -> None:
        """Deliver ``event`` to every consumer, then raise if any of them failed."""
        failures: List[Tuple[EventConsumer, Exception]] = []
        for consumer in self._consumers:
            try:
                consumer.on_event(event)
            # Isolation boundary: one consumer must not stop delivery to the others.
            # The failure is logged here and re-raised below, never swallowed.
            except Exception as exc:
                logger.error("%s failed on %s event", type(consumer).__name__, event.event_type.value, exc_info=exc)
                failures.append((consumer, exc))
        if failures:
            raise EventDeliveryError(event, failures) from failures[0][1]
