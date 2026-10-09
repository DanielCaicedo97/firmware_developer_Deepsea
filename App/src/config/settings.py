"""Runtime settings, composed explicitly by the application entry point."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Mapping, Optional

from config.constants import (
    DEFAULT_DASHBOARD_REFRESH_S,
    DEFAULT_RECEIVE_TIMEOUT_S,
    DEFAULT_RECENT_FAULT_LIMIT,
    DEFAULT_STATS_INTERVAL_S,
    DIAGNOSTIC_BASE_ID,
    FAULT_ID,
    FIRST_FRAME_MAX_DECLARED_LENGTH,
    MAX_DIAGNOSTIC_LENGTH,
    MIN_SEGMENTED_MESSAGE_LENGTH,
    MODULE_COUNT,
    TELEMETRY_BASE_ID,
)
from models.message import FramingMode


@dataclass(frozen=True)
class CommunicationConfig:
    """Settings for the communication (bus I/O) layer.

    ``socket_receive_buffer_bytes`` sets the kernel socket receive buffer
    (``SO_RCVBUF``) when not ``None``; otherwise the OS default is kept.
    """

    interface: str
    receive_timeout_s: float = DEFAULT_RECEIVE_TIMEOUT_S
    socket_receive_buffer_bytes: Optional[int] = None

    def __post_init__(self) -> None:
        if not self.interface:
            raise ValueError("communication interface name must not be empty")
        if self.receive_timeout_s <= 0:
            raise ValueError("receive timeout must be positive")
        if self.socket_receive_buffer_bytes is not None and self.socket_receive_buffer_bytes <= 0:
            raise ValueError("socket receive buffer size must be positive")


@dataclass(frozen=True)
class TransportConfig:
    """Settings for the transport layer.

    ``framing`` maps each supported source ID to how it is framed. Sources not
    in the map are ignored by the transport. One reassembly context exists per
    segmented source, so the map also bounds the number of contexts.
    """

    framing: Mapping[int, FramingMode]
    max_message_length: int = MAX_DIAGNOSTIC_LENGTH

    def __post_init__(self) -> None:
        if not MIN_SEGMENTED_MESSAGE_LENGTH <= self.max_message_length <= FIRST_FRAME_MAX_DECLARED_LENGTH:
            raise ValueError(f"max message length out of range: {self.max_message_length}")
        object.__setattr__(self, "framing", MappingProxyType(dict(self.framing)))


class OutputMode(Enum):
    """How application events are presented."""

    NORMAL = "normal"
    GRADER = "grader"


@dataclass(frozen=True)
class OutputConfig:
    """Settings for the application and output layers.

    ``stats_interval_s`` is how often stats are reported (ADAPTER.md: at least
    every few seconds); ``dashboard_refresh_s`` throttles dashboard redraws
    between stats reports; ``recent_fault_limit`` bounds the fault history.
    """

    mode: OutputMode = OutputMode.NORMAL
    stats_interval_s: float = DEFAULT_STATS_INTERVAL_S
    dashboard_refresh_s: float = DEFAULT_DASHBOARD_REFRESH_S
    recent_fault_limit: int = DEFAULT_RECENT_FAULT_LIMIT

    def __post_init__(self) -> None:
        if self.stats_interval_s <= 0:
            raise ValueError("stats interval must be positive")
        if self.dashboard_refresh_s <= 0:
            raise ValueError("dashboard refresh interval must be positive")
        if self.recent_fault_limit <= 0:
            raise ValueError("recent fault limit must be positive")


@dataclass(frozen=True)
class LoggingConfig:
    """Settings for diagnostic logging, which always goes to stderr."""

    debug: bool = False


@dataclass(frozen=True)
class ApplicationConfig:
    """Top-level configuration grouping every layer's settings."""

    communication: CommunicationConfig
    transport: TransportConfig
    output: OutputConfig = field(default_factory=OutputConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)


def build_framing_map(module_count: int = MODULE_COUNT) -> dict[int, FramingMode]:
    """Return the challenge framing map for ``module_count`` power modules.

    Telemetry and fault IDs carry single-frame messages; each module's
    identification ID carries segmented messages.
    """
    if module_count <= 0:
        raise ValueError("module count must be positive")
    framing = {FAULT_ID: FramingMode.SINGLE_FRAME}
    for module_index in range(module_count):
        framing[TELEMETRY_BASE_ID + module_index] = FramingMode.SINGLE_FRAME
        framing[DIAGNOSTIC_BASE_ID + module_index] = FramingMode.SEGMENTED
    return framing


def build_application_config(
    interface: str,
    debug: bool = False,
    grader: bool = False,
    module_count: int = MODULE_COUNT,
    max_message_length: int = MAX_DIAGNOSTIC_LENGTH,
) -> ApplicationConfig:
    """Build the application configuration from CLI-level values."""
    return ApplicationConfig(
        communication=CommunicationConfig(interface=interface),
        transport=TransportConfig(
            framing=build_framing_map(module_count),
            max_message_length=max_message_length,
        ),
        output=OutputConfig(mode=OutputMode.GRADER if grader else OutputMode.NORMAL),
        logging=LoggingConfig(debug=debug),
    )
