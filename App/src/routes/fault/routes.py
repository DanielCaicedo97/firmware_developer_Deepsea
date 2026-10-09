"""Fault routes: the fault ID → fault decoder → fault controller."""

from __future__ import annotations

from config.constants import FAULT_ID
from controllers.base_controller import BaseController
from protocol.fault import FaultResult, decode_fault
from routes.common.controller_route import DECODER_ERRORS, ControllerRoute, Decoder
from routes.common.router import SubRouter

FAULT_ROUTER_NAME = "fault"


def build_fault_router(
    controller: BaseController[FaultResult],
    decoder: Decoder[FaultResult] = decode_fault,
) -> SubRouter:
    """Return a subrouter sending the fault ID to ``controller``."""
    router = SubRouter(FAULT_ROUTER_NAME, expected_errors=DECODER_ERRORS)
    router.add_route(FAULT_ID, ControllerRoute(decoder, controller))
    return router
