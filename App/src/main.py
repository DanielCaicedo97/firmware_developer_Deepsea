"""DeepSea CAN diagnostic tool entry point.

Parses the CLI, composes the communication and transport layers explicitly and
runs the single-threaded receive loop. Logging goes to stderr only.

Usage::

    python3 App/src/main.py --iface vcan0 [--debug]
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Optional, Sequence

from communication.interface import CommunicationError, CommunicationInterface
from communication.socketcan import SocketCanInterface
from config.settings import LoggingConfig, build_application_config
from models.can_frame import CANFrame
from models.message import Message
from transport.can_transport import CanTransport
from transport.listener import TransportListener
from transport.transport import Transport

logger = logging.getLogger("deepsea")


class LoggingMessageListener(TransportListener):
    """Temporary upper layer: logs complete messages to stderr.

    Stands in for the router until protocol decoding is implemented.
    """

    def on_message(self, message: Message) -> None:
        """Log one complete message at debug level."""
        logger.debug(
            "message %#x (%s, %d frame(s)): %s",
            message.message_id,
            message.metadata.framing.value,
            message.metadata.frame_count,
            message.payload.hex(),
        )


def parse_arguments(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="DeepSea CAN diagnostic tool")
    parser.add_argument("--iface", required=True, help="CAN interface to monitor (e.g. vcan0)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging on stderr")
    return parser.parse_args(argv)


def configure_logging(config: LoggingConfig) -> None:
    """Route all logging to stderr so stdout stays reserved for program output."""
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.DEBUG if config.debug else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def run_receive_loop(communication: CommunicationInterface[CANFrame], transport: Transport[CANFrame]) -> None:
    """Receive frames forever and hand each valid one to the transport."""
    while True:
        frame = communication.receive()
        if frame is not None:
            transport.process(frame)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Compose the application and run it until interrupted."""
    args = parse_arguments(argv)
    config = build_application_config(interface=args.iface, debug=args.debug)
    configure_logging(config.logging)

    transport = CanTransport(config.transport)
    transport.add_listener(LoggingMessageListener())
    communication = SocketCanInterface(config.communication)

    try:
        with communication:
            run_receive_loop(communication, transport)
    except CommunicationError as exc:
        logger.error("%s", exc)
        return 1
    except KeyboardInterrupt:
        logger.debug("interrupted, shutting down")
    return 0


if __name__ == "__main__":
    sys.exit(main())
