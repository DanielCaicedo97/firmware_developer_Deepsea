"""Telemetry routes: telemetry IDs → telemetry decoder → telemetry controller."""

from __future__ import annotations

from config.constants import TELEMETRY_BASE_ID
from controllers.base_controller import BaseController
from protocol.telemetry import TelemetryResult, decode_telemetry
from routes.common.controller_route import DECODER_ERRORS, ControllerRoute, Decoder, per_module_ids
from routes.common.router import SubRouter

TELEMETRY_ROUTER_NAME = "telemetry"


def build_telemetry_router(
    controller: BaseController[TelemetryResult],
    decoder: Decoder[TelemetryResult] = decode_telemetry,
) -> SubRouter:
    """Return a subrouter sending every module's telemetry ID to ``controller``."""
    router = SubRouter(TELEMETRY_ROUTER_NAME, expected_errors=DECODER_ERRORS)
    router.add_routes(per_module_ids(TELEMETRY_BASE_ID), ControllerRoute(decoder, controller))
    return router
