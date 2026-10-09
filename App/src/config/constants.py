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

# --- Telemetry payload (CHALLENGE.md "Power module telemetry") ----------------

# voltage_raw u16 LE, current_raw u16 LE, temp_raw u8, status u8, seq u16 LE.
TELEMETRY_PAYLOAD_FORMAT = "<HHBBH"
TELEMETRY_PAYLOAD_LENGTH = 8

VOLTAGE_SCALE_V = 0.1
CURRENT_SCALE_A = 0.01
TEMPERATURE_OFFSET_C = 40

STATUS_ENABLED_MASK = 0x01
STATUS_FAULT_MASK = 0x02
STATUS_DERATED_MASK = 0x04

# --- Fault payload (CHALLENGE.md "Fault code") --------------------------------

# byte0 module_id, byte1 fault_code, bytes 2-7 = 0.
FAULT_PAYLOAD_LENGTH = 8
FAULT_MODULE_OFFSET = 0
FAULT_CODE_OFFSET = 1
FAULT_RESERVED_OFFSET = 2

# --- Identification string (CHALLENGE.md example, supplied generator) ---------

# The generator sends "SN:<serial> FW:<firmware> #<counter>" as ASCII; the
# CHALLENGE.md dashboard example shows the same text without the counter.
DIAGNOSTIC_TEXT_ENCODING = "ascii"
DIAGNOSTIC_FIELD_SEPARATOR = " "
SERIAL_NUMBER_PREFIX = "SN:"
FIRMWARE_VERSION_PREFIX = "FW:"
COUNTER_PREFIX = "#"

# --- Runtime defaults -----------------------------------------------------------

DEFAULT_RECEIVE_TIMEOUT_S = 0.5

# ADAPTER.md: stats at least once every few seconds, even with no traffic.
DEFAULT_STATS_INTERVAL_S = 1.0
DEFAULT_DASHBOARD_REFRESH_S = 0.2
DEFAULT_RECENT_FAULT_LIMIT = 5

NANOSECONDS_PER_SECOND = 1_000_000_000
