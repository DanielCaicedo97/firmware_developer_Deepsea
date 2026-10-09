"""Glue shared by the domain routes: decoder → controller handlers."""

from __future__ import annotations

from typing import Callable, Generic, Tuple, TypeVar

from config.constants import MODULE_COUNT
from controllers.base_controller import BaseController
from controllers.results import ControllerResult
from models.message import Message
from protocol.common import ProtocolDecodeError

ResultT = TypeVar("ResultT")
Decoder = Callable[[Message], ResultT]

# Decoders raise ProtocolDecodeError for invalid bus input; the subrouter turns
# it into a HANDLER_FAILED result instead of stopping the receive loop.
DECODER_ERRORS = (ProtocolDecodeError,)


def per_module_ids(base_id: int) -> Tuple[int, ...]:
    """Return the ``MODULE_COUNT`` consecutive IDs starting at ``base_id``."""
    return tuple(range(base_id, base_id + MODULE_COUNT))


class ControllerRoute(Generic[ResultT]):
    """Route handler: decodes a message, then delegates the result to a controller.

    The route holds no logic of its own. Decoding stays in the protocol
    decoder and application behavior in the controller; a decode error
    propagates before the controller is called. Returns the controller's
    ``ControllerResult`` (its ``decoded`` field is the decoder result), which
    the subrouter reports in its ``DispatchResult``.
    """

    def __init__(self, decoder: Decoder[ResultT], controller: BaseController[ResultT]) -> None:
        self._decoder = decoder
        self._controller = controller

    def __call__(self, message: Message) -> ControllerResult:
        """Decode ``message`` and hand the result to the controller."""
        return self._controller.handle(self._decoder(message), message)
