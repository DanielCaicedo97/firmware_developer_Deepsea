"""Diagnostic routes: identification IDs → diagnostic decoder → diagnostic controller."""

from __future__ import annotations

from config.constants import DIAGNOSTIC_BASE_ID
from controllers.base_controller import BaseController
from protocol.diagnostic import DiagnosticResult, decode_diagnostic
from routes.common.controller_route import DECODER_ERRORS, ControllerRoute, Decoder, per_module_ids
from routes.common.router import SubRouter

DIAGNOSTIC_ROUTER_NAME = "diagnostic"


def build_diagnostic_router(
    controller: BaseController[DiagnosticResult],
    decoder: Decoder[DiagnosticResult] = decode_diagnostic,
) -> SubRouter:
    """Return a subrouter sending every module's identification ID to ``controller``."""
    router = SubRouter(DIAGNOSTIC_ROUTER_NAME, expected_errors=DECODER_ERRORS)
    router.add_routes(per_module_ids(DIAGNOSTIC_BASE_ID), ControllerRoute(decoder, controller))
    return router
