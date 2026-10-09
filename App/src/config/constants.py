"""Protocol and link-layer constants.

These values are fixed by CHALLENGE.md or by the Linux SocketCAN ABI. They are
not runtime settings; runtime settings live in ``settings.py``.
"""

# --- Classic CAN / SocketCAN ABI (linux/can.h) -------------------------------

# struct can_frame: canid_t (u32), dlc (u8), 3 padding bytes, 8 data bytes.
CAN_FRAME_FORMAT = "=IB3x8s"
CAN_MAX_DATA_LENGTH = 8

CAN_STANDARD_ID_MASK = 0x7FF
CAN_EXTENDED_FRAME_FLAG = 0x80000000
CAN_REMOTE_FRAME_FLAG = 0x40000000
CAN_ERROR_FRAME_FLAG = 0x20000000
CAN_FLAGS_MASK = CAN_EXTENDED_FRAME_FLAG | CAN_REMOTE_FRAME_FLAG | CAN_ERROR_FRAME_FLAG

# --- Challenge bus identifiers ------------------------------------------------

MODULE_COUNT = 4

TELEMETRY_BASE_ID = 0x100
FAULT_ID = 0x1F0
DIAGNOSTIC_BASE_ID = 0x6F0

NOISE_ID_FIRST = 0x200
NOISE_ID_LAST = 0x2FF

# --- ISO 15765-2-style segmentation (diagnostic identification string) -------

PCI_TYPE_MASK = 0xF0
PCI_FIRST_FRAME = 0x10
PCI_CONSECUTIVE_FRAME = 0x20

FIRST_FRAME_LENGTH_HIGH_MASK = 0x0F
FIRST_FRAME_HEADER_SIZE = 2
CONSECUTIVE_FRAME_HEADER_SIZE = 1

# The 12-bit First Frame length field cannot declare more than this.
FIRST_FRAME_MAX_DECLARED_LENGTH = 0xFFF

SEQUENCE_NUMBER_MASK = 0x0F
FIRST_SEQUENCE_NUMBER = 1

# CHALLENGE.md: messages are always longer than 7 bytes and never longer than 64.
MIN_SEGMENTED_MESSAGE_LENGTH = 8
MAX_DIAGNOSTIC_LENGTH = 64

# --- Runtime defaults -----------------------------------------------------------

DEFAULT_RECEIVE_TIMEOUT_S = 0.5
