"""Composes the domain routes into the central router.

Telemetry IDs, the fault ID and the identification IDs reach their domain
controller through their decoder. Noise and every other ID are left
unregistered, so they produce ``ROUTE_NOT_FOUND`` and reach nothing.
"""

from __future__ import annotations

from typing import Optional

from controllers.base_controller import BaseController
from protocol.diagnostic import DiagnosticResult
from protocol.fault import FaultResult
from protocol.telemetry import TelemetryResult
from routes.common.router import RootRouter
from routes.diagnostic.routes import build_diagnostic_router
from routes.fault.routes import build_fault_router
from routes.telemetry.routes import build_telemetry_router


def init_routes(
    telemetry_controller: BaseController[TelemetryResult],
    fault_controller: BaseController[FaultResult],
    diagnostic_controller: BaseController[DiagnosticResult],
    root: Optional[RootRouter] = None,
) -> RootRouter:
    """Register every domain router on ``root`` (a new one if omitted) and return it."""
    root = RootRouter() if root is None else root
    root.include_router(build_telemetry_router(telemetry_controller))
    root.include_router(build_fault_router(fault_controller))
    root.include_router(build_diagnostic_router(diagnostic_controller))
    return root
