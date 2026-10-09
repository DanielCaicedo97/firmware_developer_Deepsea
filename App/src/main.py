"""DeepSea CAN diagnostic tool entry point and composition root.

Builds every layer explicitly, connects them and runs the single-threaded
receive loop until interrupted (Ctrl+C or SIGTERM), then emits the final stats.
Normal mode draws a terminal dashboard; ``--grader`` writes ADAPTER.md NDJSON
to stdout. Logging always goes to stderr.

Usage::

    python3 App/src/main.py --iface vcan0 [--grader] [--debug]
"""

from __future__ import annotations

import argparse
import functools
import logging
import signal
import sys
from types import FrameType
from typing import Optional, Sequence

from communication.interface import CommunicationError, CommunicationInterface
from communication.socketcan import SocketCanInterface
from config.constants import NANOSECONDS_PER_SECOND
from config.settings import ApplicationConfig, LoggingConfig, OutputConfig, OutputMode, build_application_config
from controllers.application_controller import ApplicationController
from controllers.diagnostic import DiagnosticController
from controllers.fault import FaultController
from controllers.telemetry import TelemetryController
from models.can_frame import CANFrame
from output.dashboard import Dashboard
from output.grader import GraderOutput
from routes.routes_init import init_routes
from services.application_state import ApplicationState
from services.event_publisher import EventConsumer, EventDeliveryError, EventPublisher
from services.stats_service import StatsService
from transport.can_transport import CanTransport
from transport.transport import Transport

logger = logging.getLogger("deepsea")


class ShutdownRequest:
    """Turns SIGTERM into a clean stop of the receive loop."""

    def __init__(self) -> None:
        self.requested = False

    def request(self, signum: int, frame: Optional[FrameType]) -> None:
        """Signal handler: ask the loop to stop after the current receive."""
        self.requested = True

    def keep_running(self) -> bool:
        """Run condition for the application loop."""
        return not self.requested


def parse_arguments(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="DeepSea CAN diagnostic tool")
    parser.add_argument("--iface", required=True, help="CAN interface to monitor (e.g. vcan0)")
    parser.add_argument("--grader", action="store_true", help="Write ADAPTER.md NDJSON events to stdout")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging on stderr")
    return parser.parse_args(argv)


def configure_logging(config: LoggingConfig) -> None:
    """Route all logging to stderr so stdout stays reserved for program output."""
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.DEBUG if config.debug else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def seconds_to_ns(seconds: float) -> int:
    """Convert a configured duration to nanoseconds."""
    return int(seconds * NANOSECONDS_PER_SECOND)


def build_output(config: OutputConfig, state: ApplicationState) -> EventConsumer:
    """Return the one output consumer for the configured mode; both write to stdout."""
    if config.mode is OutputMode.GRADER:
        return GraderOutput(sys.stdout)
    return Dashboard(state, sys.stdout, seconds_to_ns(config.dashboard_refresh_s))


def build_application(config: ApplicationConfig, transport: Transport[CANFrame]) -> ApplicationController:
    """Build state, stats, publisher, output, controllers and routes, and attach them to ``transport``."""
    state = ApplicationState(recent_fault_limit=config.output.recent_fault_limit)
    stats = StatsService(seconds_to_ns(config.output.stats_interval_s))
    publisher = EventPublisher()
    publisher.register(build_output(config.output, state))
    root = init_routes(
        TelemetryController(state, stats, publisher),
        FaultController(state, stats, publisher),
        DiagnosticController(state, stats, publisher),
    )
    application = ApplicationController(root.dispatch, stats, publisher)
    transport.add_listener(application)
    return application


def run(
    application: ApplicationController,
    communication: CommunicationInterface[CANFrame],
    transport: Transport[CANFrame],
) -> int:
    """Open the bus, process frames until stopped, then emit final stats and close."""
    try:
        communication.open()
    except CommunicationError as exc:
        logger.error("%s", exc)
        return 1
    shutdown = ShutdownRequest()
    signal.signal(signal.SIGTERM, shutdown.request)
    try:
        application.run(functools.partial(transport.receive_from, communication), shutdown.keep_running)
    except (CommunicationError, EventDeliveryError) as exc:
        logger.error("%s", exc)
        return 1
    except KeyboardInterrupt:
        logger.debug("interrupted, shutting down")
    finally:
        stop(application, communication)
    return 0


def stop(application: ApplicationController, communication: CommunicationInterface[CANFrame]) -> None:
    """Publish the final stats, then close the bus even if the output failed."""
    try:
        application.shutdown()
    except EventDeliveryError as exc:
        logger.error("final stats not delivered: %s", exc)
    finally:
        communication.close()


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Compose the application and run it until interrupted."""
    args = parse_arguments(argv)
    config = build_application_config(interface=args.iface, debug=args.debug, grader=args.grader)
    configure_logging(config.logging)
    communication = SocketCanInterface(config.communication)
    transport = CanTransport(config.transport)
    application = build_application(config, transport)
    return run(application, communication, transport)


if __name__ == "__main__":
    sys.exit(main())
