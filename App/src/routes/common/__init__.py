"""Generic router behavior and dispatch results shared by every domain route."""

from routes.common.results import DispatchResult, DispatchStatus
from routes.common.router import BaseRouter, Handler, RootRouter, RouteRegistrationError, SubRouter

__all__ = [
    "BaseRouter",
    "DispatchResult",
    "DispatchStatus",
    "Handler",
    "RootRouter",
    "RouteRegistrationError",
    "SubRouter",
]
