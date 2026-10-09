"""Generic routing: a root router delegating to per-domain subrouters.

Routers read only a complete message's ID. They never open sockets, reassemble
frames, decode payloads, hold message state or produce output. Nothing here
knows a decoder or a controller; the challenge routes are composed in the
domain ``routes`` modules and ``routes.routes_init``.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Generic, Iterable, Optional, Tuple, Type, TypeVar

from config.constants import CAN_STANDARD_ID_MASK
from models.message import Message
from routes.common.results import DispatchResult, DispatchStatus

TargetT = TypeVar("TargetT")
Handler = Callable[[Message], Any]

ROOT_ROUTER_NAME = "root"


class RouteRegistrationError(ValueError):
    """Raised when a route is invalid or conflicts with an existing one."""


class BaseRouter(Generic[TargetT]):
    """Owns one router's table of message ID → target.

    The target is a handler for a subrouter and a subrouter for the root.
    Each instance has its own table; registration validates every ID and never
    overwrites an existing route.
    """

    def __init__(self, name: str) -> None:
        if not isinstance(name, str) or not name:
            raise RouteRegistrationError("router name must be a non-empty string")
        self._name = name
        self._routes: Dict[int, TargetT] = {}

    @property
    def name(self) -> str:
        """The router's name, reported in dispatch results."""
        return self._name

    @property
    def can_ids(self) -> Tuple[int, ...]:
        """Registered message IDs, in ascending order."""
        return tuple(sorted(self._routes))

    def handles(self, can_id: int) -> bool:
        """Return True if ``can_id`` has a route in this router."""
        return can_id in self._routes

    def _lookup(self, can_id: int) -> Optional[TargetT]:
        """Return the target registered for ``can_id``, or ``None``."""
        return self._routes.get(can_id)

    def _register_all(self, can_ids: Iterable[int], target: TargetT) -> None:
        """Register ``target`` for every ID, or for none if any ID is rejected."""
        ids = tuple(can_ids)
        if not ids:
            raise RouteRegistrationError(f"{self._name}: no message IDs given")
        if len(set(ids)) != len(ids):
            raise RouteRegistrationError(f"{self._name}: duplicate IDs in one registration: {ids}")
        for can_id in ids:
            self._validate_new_id(can_id)
        for can_id in ids:
            self._routes[can_id] = target

    def _validate_new_id(self, can_id: int) -> None:
        """Reject IDs that are not 11-bit integers or are already routed."""
        if isinstance(can_id, bool) or not isinstance(can_id, int) or not 0 <= can_id <= CAN_STANDARD_ID_MASK:
            raise RouteRegistrationError(f"{self._name}: invalid message ID {can_id!r}")
        if can_id in self._routes:
            raise RouteRegistrationError(f"{self._name}: message ID {can_id:#x} is already routed")


class SubRouter(BaseRouter[Handler]):
    """Groups the handlers of one message category.

    ``expected_errors`` are the exceptions a handler raises for invalid input;
    they become ``HANDLER_FAILED`` results. Any other exception is a
    programming error and propagates. The subrouter holds no message state.

    A root router indexes the subrouter's IDs when it includes it, then seals
    it, so a later registration fails loudly instead of being silently
    unreachable.
    """

    def __init__(self, name: str, expected_errors: Tuple[Type[Exception], ...] = ()) -> None:
        super().__init__(name)
        self._expected_errors = expected_errors
        self._sealed = False

    @property
    def sealed(self) -> bool:
        """True once a root router has included this subrouter."""
        return self._sealed

    def seal(self) -> None:
        """Forbid further registrations (called by ``RootRouter.include_router``)."""
        self._sealed = True

    def add_route(self, can_id: int, handler: Handler) -> None:
        """Register ``handler`` for one message ID."""
        self.add_routes((can_id,), handler)

    def add_routes(self, can_ids: Iterable[int], handler: Handler) -> None:
        """Register one ``handler`` for several message IDs, all or none."""
        if self._sealed:
            raise RouteRegistrationError(f"{self.name}: already included in a root router; register routes first")
        if not callable(handler):
            raise RouteRegistrationError(f"{self.name}: handler {handler!r} is not callable")
        self._register_all(can_ids, handler)

    def route(self, *can_ids: int) -> Callable[[Handler], Handler]:
        """Decorator form of ``add_routes``; returns the handler unchanged."""

        def register(handler: Handler) -> Handler:
            """Register ``handler`` for the decorator's IDs."""
            self.add_routes(can_ids, handler)
            return handler

        return register

    def dispatch(self, message: Message) -> DispatchResult:
        """Invoke the handler registered for ``message.message_id``."""
        handler = self._lookup(message.message_id)
        if handler is None:
            return DispatchResult(DispatchStatus.HANDLER_NOT_FOUND, message, router_name=self.name)
        try:
            result = handler(message)
        except self._expected_errors as exc:
            return DispatchResult(DispatchStatus.HANDLER_FAILED, message, router_name=self.name, error=exc)
        return DispatchResult(DispatchStatus.SUCCESS, message, router_name=self.name, result=result)


class RootRouter(BaseRouter[SubRouter]):
    """Finds the subrouter for a message ID and delegates dispatch to it.

    ``include_router`` indexes a subrouter's IDs and seals it, so a subrouter
    must be fully registered before it is included. The root reads only the
    message ID; it never decodes payloads.
    """

    def __init__(self, name: str = ROOT_ROUTER_NAME) -> None:
        super().__init__(name)

    def include_router(self, subrouter: SubRouter) -> None:
        """Route every ID of ``subrouter`` to it and seal it; all or none."""
        if not isinstance(subrouter, SubRouter):
            raise RouteRegistrationError(f"{self.name}: {subrouter!r} is not a SubRouter")
        self._register_all(subrouter.can_ids, subrouter)
        subrouter.seal()

    def dispatch(self, message: Message) -> DispatchResult:
        """Dispatch ``message`` through its subrouter, or report no route."""
        subrouter = self._lookup(message.message_id)
        if subrouter is None:
            return DispatchResult(DispatchStatus.ROUTE_NOT_FOUND, message)
        return subrouter.dispatch(message)
