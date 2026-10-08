# Code Standards

## 1. Purpose

This document defines the coding standards and development conventions for the DeepSea CAN Diagnostic Tool.

The objective is to keep the code:

* Readable
* Maintainable
* Testable
* Predictable
* Easy to review
* Suitable for automated static analysis
* Consistent with Python 3 standards
* Compliant with the challenge restrictions

The project should favor **simple, explicit, and maintainable solutions over unnecessary abstraction or complexity**.

---

# 2. Technology Constraints

The implementation must follow the technical restrictions defined by the challenge.

## 2.1 Python Version

* Use Python 3.
* Code must be compatible with the Python 3 version available on the Raspberry Pi.
* Prefer standard-library functionality.

## 2.2 Allowed Libraries

Only the Python standard library may be used.

Examples of allowed modules include:

```python
import argparse
import json
import logging
import socket
import struct
import sys
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional
```

Third-party dependencies must not be introduced.

## 2.3 Prohibited Libraries and APIs

The following are explicitly prohibited:

* `python-can`
* `can-isotp`
* `cantools`
* `canmatrix`
* Any CAN message decoding library
* Any CAN filtering library
* Any ISO-TP library
* Linux kernel `CAN_ISOTP`

The implementation must perform CAN frame handling and diagnostic message reassembly directly using the Python standard library.

## 2.4 CAN Transmission

The application is **receive-only**.

The application must never transmit CAN frames.

Do not use:

```python
send()
sendto()
```

or equivalent CAN transmission mechanisms.

The CAN socket must only be used for receiving traffic.

---

# 3. General Python Style

Follow standard Python conventions based on PEP 8.

## 3.1 Naming

Use:

* `snake_case` for variables and functions
* `PascalCase` for classes
* `UPPER_SNAKE_CASE` for module-level constants
* Descriptive names instead of abbreviations

Good:

```python
frames_processed
module_state
diagnostic_context
sequence_number
```

Avoid:

```python
fp
ms
ctx
seq
```

Short names are acceptable when their meaning is universally clear:

```python
i
j
fd
id
```

However, descriptive names are preferred in application logic.

---

# 4. Constants

Magic numbers must not be scattered throughout the implementation.

CAN identifiers, protocol limits, timing values, and frame sizes should be defined as constants.

Example:

```python
TELEMETRY_BASE_ID = 0x100
FAULT_ID = 0x1F0
DIAGNOSTIC_BASE_ID = 0x6F0

MODULE_COUNT = 4
MAX_DIAGNOSTIC_LENGTH = 64
MAX_CAN_DATA_LENGTH = 8
```

Prefer:

```python
if message_id == FAULT_ID:
```

over:

```python
if message_id == 0x1F0:
```

This makes the protocol easier to understand and modify.

---

# 5. Imports

Imports must be:

1. Standard library imports
2. Local project imports

Separate groups with a blank line.

Example:

```python
import argparse
import socket
import struct
import time

from dataclasses import dataclass

from can_receiver import CanReceiver
from diagnostic import DiagnosticReassembler
```

Unused imports are not allowed.

Imports should be placed at the top of the module unless there is a documented reason to perform a local import.

---

# 6. Functions

Functions should have a **single clear responsibility**.

Avoid large functions that perform several unrelated operations.

Bad:

```python
def process_everything():
    # receive CAN frame
    # filter frame
    # decode telemetry
    # decode faults
    # reassemble diagnostics
    # update statistics
    # print dashboard
```

Prefer:

```python
def receive_frame():
    ...

def classify_frame():
    ...

def decode_telemetry():
    ...

def decode_fault():
    ...

def process_diagnostic_frame():
    ...

def update_statistics():
    ...
```

This makes the system easier to test and reduces cognitive complexity.

## 6.1 Function Length

Functions should generally remain short and focused.

As a guideline:

* Prefer less than 30 lines.
* Functions above approximately 50 lines should have a clear justification.
* Long functions should be reviewed for possible decomposition.

Line count alone is not the deciding factor. A slightly longer function can be acceptable if splitting it would make the design less clear.

---

# 7. Type Hints

Type hints should be used for application logic, especially for:

* Function parameters
* Return values
* Data structures
* Protocol-related objects
* State objects

Example:

```python
def decode_telemetry(
    data: bytes,
    module_id: int,
) -> Telemetry:
    ...
```

Avoid unnecessary complexity in type annotations.

The goal is to make interfaces understandable, not to create complicated type systems.

---

# 8. Data Structures

Use appropriate standard-library structures.

Prefer `dataclass` for structured application state.

Example:

```python
@dataclass
class Telemetry:
    module_id: int
    sequence: int
    voltage: float
    current: float
    temperature: float
```

Use `Enum` when a finite set of named states exists.

Example:

```python
class DiagnosticState(Enum):
    IDLE = 1
    RECEIVING = 2
```

Avoid using unstructured dictionaries everywhere when a clear domain object would make the code easier to understand.

---

# 9. CAN Frame Handling

CAN frames must be handled explicitly using SocketCAN and the Python standard library.

The CAN interface should be isolated behind a small receiving component.

Conceptually:

```text
SocketCAN
    │
    ▼
CAN Receiver
    │
    ▼
Frame Classification
    │
    ├── Telemetry
    ├── Fault
    └── Diagnostic
```

The rest of the application should not need to know the low-level socket implementation.

## 9.1 Socket Creation

Use:

```python
socket.socket(
    socket.AF_CAN,
    socket.SOCK_RAW,
    socket.CAN_RAW,
)
```

and bind to the requested interface.

Example:

```python
sock.bind((interface,))
```

## 9.2 Receive Only

The CAN socket must only receive frames.

Example:

```python
frame = sock.recv(...)
```

No CAN transmission is permitted.

---

# 10. Frame Filtering

CAN frames must be classified before decoding.

The application should only process the CAN identifiers relevant to the challenge.

Conceptually:

```text
Incoming CAN Frame
        │
        ▼
    CAN ID
        │
        ├── Telemetry → Decode
        │
        ├── Fault → Decode
        │
        ├── Diagnostic → Reassembly
        │
        └── Other → Ignore
```

Unrelated traffic must not affect application state.

In particular, noise traffic in the `0x200–0x2FF` range must not be counted as real processed frames.

---

# 11. Protocol Decoding

Protocol decoding must be explicit and deterministic.

Avoid hidden conversions or implicit assumptions.

For binary fields, use `struct` where appropriate.

Example:

```python
value = struct.unpack_from("<H", data, offset)[0]
```

Protocol-specific offsets, lengths, and masks should be represented by named constants when practical.

Example:

```python
SEQUENCE_MASK = 0x0F
```

rather than repeatedly using unexplained literals.

---

# 12. Diagnostic Reassembly

Diagnostic messages are stateful.

Each module must have an independent reassembly context.

The architecture should conceptually maintain:

```text
Module 0 → Diagnostic Context 0
Module 1 → Diagnostic Context 1
Module 2 → Diagnostic Context 2
Module 3 → Diagnostic Context 3
```

A single shared diagnostic buffer for all modules is not acceptable.

## 12.1 Independent State

Interleaved frames from different modules must not corrupt each other's state.

Example:

```text
Module 0 → FF
Module 1 → FF
Module 2 → FF
Module 3 → FF
Module 0 → CF
Module 2 → CF
Module 1 → CF
Module 3 → CF
```

Each module must continue its own reassembly independently.

## 12.2 First Frame

A valid First Frame starts a new diagnostic message.

If a new First Frame arrives while a previous message for the same module is being reassembled:

1. Abandon the previous message.
2. Reset the corresponding context.
3. Start the new message.

The old state must not remain allocated.

## 12.3 Consecutive Frames

Consecutive Frames must only be accepted when a valid reassembly context exists.

An orphan Consecutive Frame must be ignored.

## 12.4 Sequence Numbers

Sequence numbers must be validated according to the diagnostic protocol.

An unexpected sequence number must cause the current reassembly attempt to be abandoned.

The implementation must not attempt to silently repair corrupted message ordering.

## 12.5 Length Validation

Diagnostic messages with an invalid length must be rejected.

The challenge defines lengths greater than 64 bytes as invalid.

Example:

```python
if length > MAX_DIAGNOSTIC_LENGTH:
    reject_message()
```

## 12.6 Bounded State

Diagnostic buffers must remain bounded.

A malformed or repeatedly abandoned diagnostic sequence must not cause:

* Unbounded memory growth
* Accumulation of stale buffers
* Increasing numbers of orphan contexts

A diagnostic context should contain only the state required for the current message.

---

# 13. State Management

State should be explicit.

Avoid hidden global mutable state.

Prefer:

```python
class DiagnosticReassembler:
    def __init__(self):
        self.contexts = {}
```

over several unrelated global variables.

State transitions should be easy to identify.

For example:

```text
IDLE
 │
 │ First Frame
 ▼
RECEIVING
 │
 ├── valid CF ────────────┐
 │                         │
 │                         ▼
 │                     RECEIVING
 │
 ├── complete ───────────► IDLE
 │
 ├── invalid sequence ───► IDLE
 │
 ├── invalid length ─────► IDLE
 │
 └── restart FF ─────────► RECEIVING
```

---

# 14. Error Handling

Errors should be handled at the appropriate level.

Do not use broad exception handling unnecessarily.

Avoid:

```python
try:
    ...
except Exception:
    pass
```

This can hide programming errors and make debugging difficult.

Prefer specific exceptions:

```python
try:
    frame = sock.recv(FRAME_SIZE)
except OSError as exc:
    ...
```

Errors that prevent the application from operating should be reported clearly.

Malformed CAN traffic should generally be treated as input that must be rejected safely, rather than as an application crash.

---

# 15. Logging

Logging must not interfere with grader output.

The challenge defines:

* `stdout` → grader NDJSON
* `stderr` → diagnostic/logging information

Therefore:

```text
stdout
  └── Machine-readable NDJSON

stderr
  └── Human-readable diagnostics
```

Do not write debugging messages to stdout in grader mode.

Avoid:

```python
print("Received frame!")
```

when running in grader mode.

Use a logging mechanism directed to stderr instead.

---

# 16. Grader Mode

Grader mode must produce valid NDJSON following `ADAPTER.md` exactly.

Each event must be emitted as one complete JSON object per line, and every line carries a `"type"` field.

The four event types and their exact fields are:

```json
{"type": "telemetry", "module": 0, "seq": 4821, "voltage": 412.3, "current": 118.55, "temp_c": 47, "enabled": true, "fault": false, "derated": false}
{"type": "fault", "module": 2, "code": 1}
{"type": "diag_complete", "can_id": "0x6f0", "string": "SN:PMU-4471-A FW:2.3.1 #1", "ts_ns": 88123456789}
{"type": "stats", "frames_processed": 15234}
```

Field rules:

* `telemetry` — one line per decoded telemetry frame. `voltage` and `current` are rounded to 2 decimals (`round(raw * 0.1, 2)`, `round(raw * 0.01, 2)`) to match the generator's own log; `temp_c` is an integer (`raw - 40`); `enabled`, `fault`, `derated` come from status bits 0, 1 and 2.
* `fault` — one line per decoded `0x1F0` frame.
* `diag_complete` — one line per successfully reassembled message only. `ts_ns` is `time.monotonic_ns()` taken at the moment reassembly completed. Abandoned attempts (orphan, out-of-order, oversized, superseded by restart) emit nothing.
* `stats` — emitted periodically (at least once every few seconds, even with no traffic) and once more right before exit. `frames_processed` counts every received frame on a real ID (telemetry, fault, diagnostic — including diagnostic frames later rejected), never noise (`0x200`–`0x2FF`).

If this section ever differs from `ADAPTER.md`, `ADAPTER.md` wins.

Every line written to stdout must be valid JSON.

No banners, prompts, debug messages, or human-readable text may be written to stdout in grader mode.

## 16.1 Flushing

Grader events must be flushed immediately or as required by the challenge.

Example:

```python
print(json.dumps(event), flush=True)
```

This ensures the grader can consume events live.

---

# 17. Statistics

Statistics should be maintained explicitly.

The `frames_processed` statistic must count only real challenge traffic:

* Telemetry frames
* Fault frames
* Diagnostic frames

Noise traffic must not increment the counter.

Example concept:

```text
Telemetry     → counted
Fault         → counted
Diagnostic    → counted
Noise         → ignored
```

Statistics should be updated in one well-defined location to avoid inconsistent counters.

---

# 18. Output Separation

The application has two different presentation responsibilities.

## Normal Mode

Designed for a human operator.

It may provide:

* Module status
* Telemetry
* Fault information
* Diagnostic messages
* Processing statistics

## Grader Mode

Designed for automated evaluation.

It must provide:

* NDJSON events
* Deterministic field names
* Live output
* No human-readable dashboard on stdout

Business logic should not depend on the presentation mode.

Prefer:

```text
CAN Reception
      │
      ▼
Protocol Processing
      │
      ▼
Application State
      │
      ├──────────────► Normal Output
      │
      └──────────────► Grader Output
```

---

# 19. Architecture and Separation of Responsibilities

The project should maintain clear separation between:

### CAN Reception

Responsible for:

* Opening the SocketCAN socket
* Binding to the requested interface
* Receiving frames

### Frame Classification

Responsible for:

* Identifying relevant CAN IDs
* Ignoring unrelated traffic

### Protocol Decoding

Responsible for:

* Telemetry decoding
* Fault decoding
* Diagnostic frame interpretation

### Diagnostic Reassembly

Responsible for:

* Per-module state
* First Frames
* Consecutive Frames
* Sequence validation
* Message completion
* Error recovery

### Application State

Responsible for:

* Latest module telemetry
* Fault state
* Completed diagnostic messages
* Statistics

### Output

Responsible for:

* Normal dashboard
* Grader NDJSON

No single component should be responsible for all of these concerns.

---

# 20. Concurrency

The diagnostic protocol requires support for multiple active module contexts.

This does **not** require unnecessary multithreading.

The preferred approach is to process frames sequentially while maintaining independent state for each module.

Example:

```text
Single CAN receive loop
        │
        ├── Module 0 context
        ├── Module 1 context
        ├── Module 2 context
        └── Module 3 context
```

The important requirement is **logical concurrency**: interleaved messages from different modules must be handled independently.

Threads should only be introduced if they provide a clear architectural benefit.

Unnecessary concurrency increases:

* Complexity
* Synchronization requirements
* Failure modes
* Static-analysis complexity

---

# 21. Comments

Comments should explain **why**, not simply repeat **what** the code does.

Avoid:

```python
# Increment counter
counter += 1
```

Prefer:

```python
# Only real challenge traffic contributes to the grader frame count.
frames_processed += 1
```

Protocol-specific comments are encouraged when they make the implementation easier to verify.

---

# 22. Docstrings

Public classes and functions should have concise docstrings.

Example:

```python
def decode_telemetry(data: bytes, module_id: int) -> Telemetry:
    """Decode one telemetry CAN payload for a power module."""
```

Docstrings should explain:

* Purpose
* Important inputs
* Important behavior
* Important constraints

Avoid excessively long docstrings for simple functions.

---

# 23. Testing

Testing should focus on protocol behavior and state transitions.

Important cases include:

### Telemetry

* Valid telemetry frame
* Multiple modules
* Sequence updates

### Faults

* Valid fault frame
* Multiple modules

### Diagnostics

* Valid First Frame
* Valid Consecutive Frames
* Complete message
* Interleaved modules
* Orphan Consecutive Frame
* Restarting First Frame
* Oversized length
* Out-of-order sequence
* Repeated abandonment

### Filtering

* Relevant CAN IDs
* Unrelated traffic
* Noise traffic

### Resource Usage

* Repeated malformed messages
* Repeated abandoned reassemblies
* Stable number of contexts
* No unbounded buffer growth

---

# 24. Testability

Core protocol logic should be testable without requiring the physical CAN interface.

Where practical, separate:

```text
Raw CAN Frame
      │
      ▼
Protocol Logic
```

so protocol logic can be tested using synthetic frames.

The actual SocketCAN receiver should remain a thin integration layer.

---

# 25. Main Entry Point

`main.py` is the application entry point.

It should primarily be responsible for:

1. Parsing command-line arguments
2. Configuring the application
3. Creating required components
4. Starting the receive/process loop
5. Handling top-level shutdown

Avoid placing the complete application implementation inside `main.py`.

The main entry point should remain easy to understand.

Expected usage:

```bash
python3 main.py --iface vcan0
```

and:

```bash
python3 main.py --iface vcan0 --grader
```

---

# 26. CLI Arguments

Command-line arguments should use `argparse`.

Example:

```python
parser = argparse.ArgumentParser(
    description="DeepSea CAN diagnostic tool"
)

parser.add_argument(
    "--iface",
    required=True,
    help="CAN interface to monitor",
)

parser.add_argument(
    "--grader",
    action="store_true",
    help="Enable machine-readable grader output",
)
```

Arguments should have clear names and help descriptions.

---

# 27. Resource Management

Resources such as sockets must be closed cleanly.

Prefer context managers where practical:

```python
with create_can_socket(interface) as sock:
    run_receiver(sock)
```

If a context manager is not appropriate, ensure cleanup is performed during shutdown.

The application should handle normal termination without leaving resources open.

---

# 28. Global Variables

Avoid mutable global state.

Constants are acceptable:

```python
MAX_DIAGNOSTIC_LENGTH = 64
```

Mutable application state should belong to an explicit object.

Avoid:

```python
modules = {}
statistics = {}
current_message = None
```

at module scope.

Prefer:

```python
class ApplicationState:
    ...
```

This makes ownership and lifecycle explicit.

---

# 29. Complexity

Code should be designed with predictable complexity.

Prefer:

```python
context = contexts.get(module_id)
```

over repeatedly scanning unrelated structures.

Protocol processing should remain approximately proportional to the number of received frames.

Avoid unnecessary:

* Nested loops
* Repeated searches
* Deep conditional chains
* Recursive processing
* Complex abstractions

The simplest correct implementation should be preferred.

---

# 30. Defensive Programming

CAN traffic is external input and must not be trusted.

The application must validate:

* CAN identifier
* Payload length
* Frame type
* Diagnostic length
* Sequence number
* Module identifier
* Reassembly state

Malformed input must not crash the application or corrupt another module's state.

---

# 31. Determinism

Protocol processing should be deterministic.

The same CAN frame sequence should produce the same:

* Decoded telemetry
* Fault events
* Diagnostic messages
* State transitions
* Frame statistics

Do not introduce randomness into protocol processing.

---

# 32. Guiding Principle

The project should follow this principle:

> **Simple enough to understand, structured enough to maintain, and explicit enough to verify.**

Correctness and robustness are more important than abstraction.

The implementation should demonstrate engineering judgment through:

* Clear boundaries
* Explicit state
* Defensive protocol handling
* Bounded resources
* Testable components
* Predictable behavior
* Minimal dependencies
* Clean interfaces

The goal is not to write the largest or most sophisticated implementation.

The goal is to write the **smallest well-structured implementation that reliably satisfies the protocol and challenge requirements**.
