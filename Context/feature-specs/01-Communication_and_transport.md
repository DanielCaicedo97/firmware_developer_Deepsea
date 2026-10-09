# Feature 01 — Communication and Transport

Read `AGENTS.md` before starting.

Read the project architecture documentation before implementing this feature:

* `docs/PROJECT_OVERVIEW.md`
* `docs/CODE_STANDARDS.md`
* `docs/architecture-context.md`

This feature establishes the communication and transport layers of the application.

The implementation must keep the communication layer independent from the application protocol. The communication layer is responsible only for receiving raw frames from the underlying transport mechanism. The transport layer is responsible for validating frames, managing transport state, and reconstructing complete messages from multiple frames.

Do not implement telemetry, fault, or diagnostic application-level decoding in this feature.

---

## Goal

Create the foundational communication and transport infrastructure required to receive CAN traffic from `vcan0` and deliver complete protocol-independent messages to the upper layers.

The design must allow the current SocketCAN implementation to be replaced by another communication mechanism in the future without requiring changes to the protocol layer.

The expected data flow is:

```text
SocketCAN / Communication
          │
          ▼
      CAN Frame
          │
          ▼
       Transport
          │
          ▼
   Complete Message
          │
          ▼
    Upper application layer
```

The implementation must support multiple diagnostic messages being reassembled concurrently through independent transport contexts.

---

## Constraints

### Runtime

* Python 3.
* Standard library only.
* Do not add external Python dependencies.
* The application must run on the provided Raspberry Pi 5 environment.
* The implementation must work with the existing `vcan0` interface.

### CAN communication

Use Linux SocketCAN directly through Python's `socket` module.

Allowed primitives include:

```python
socket.AF_CAN
socket.SOCK_RAW
socket.CAN_RAW
```

CAN frames must be packed and unpacked using the standard library, such as `struct`.

Do not use:

* `python-can`
* `can-isotp`
* `cantools`
* `canmatrix`
* Linux `CAN_ISOTP`
* Any other CAN protocol/decoding library

### Receive-only behavior

The application must never transmit CAN frames.

Do not call any CAN send API.

The communication layer must operate exclusively in receive mode.

### Architecture

Do not couple protocol/application logic to SocketCAN.

The transport layer must not know how telemetry, fault, or diagnostic payloads are interpreted.

Do not place application-level decoding inside the SocketCAN implementation.

Do not introduce a global Singleton for the communication object.

The application entry point must compose the dependencies and create the required communication instance explicitly.

### Scope

This feature includes:

* Communication interface
* SocketCAN implementation
* CAN frame representation
* Transport interface/implementation
* Diagnostic transport reassembly state
* Transport validation
* Transport-to-upper-layer notification

This feature does not include:

* Telemetry decoding
* Fault decoding
* Diagnostic payload decoding
* Message routing
* Application controller
* Dashboard
* Grader output
* Statistics service

---

## Technical Requirements

### 1. Communication interface

Create a generic communication abstraction.

The interface should expose responsibilities such as:

* Open/start communication
* Receive a frame
* Report communication errors
* Close/release communication resources

The interface must not contain CAN-specific protocol logic.

A future UART or SPI implementation should be able to implement the same communication abstraction without changing the transport or protocol layers.

---

### 2. SocketCAN implementation

Create a SocketCAN implementation of the communication interface.

The implementation must:

1. Create a raw CAN socket.
2. Bind it to the configured interface.
3. Receive CAN frames.
4. Convert the raw socket representation into the internal `CANFrame` model.
5. Never transmit frames.
6. Close the socket correctly.

The CAN interface must be provided through configuration/CLI rather than hard-coded into the transport implementation.

The challenge must support:

```bash
python3 main.py --iface vcan0
```

The communication layer itself should not decide whether the application is running in normal or grader mode.

---

### 3. CAN frame model

Create an internal representation for a received CAN frame.

The model should contain, at minimum:

* CAN identifier
* Payload/data bytes
* Payload length

If timestamps are captured at the communication boundary, they must use the appropriate monotonic source and be represented explicitly.

The model must not contain telemetry-, fault-, or diagnostic-specific fields.

Validate the basic frame structure before passing it to the transport layer.

---

### 4. Transport layer

Create a transport component that receives validated CAN frames from the communication layer.

The transport layer is responsible for:

* Frame classification at the transport level
* Transport-frame validation
* Maintaining transport state
* Reassembling multi-frame messages
* Detecting invalid transport sequences
* Abandoning invalid/incomplete messages
* Delivering completed messages to registered listeners

The transport layer must not decode application payload semantics.

---

### 5. Complete message abstraction

When a transport message has been successfully reconstructed, create a protocol-independent complete-message representation.

The message should provide enough information for the upper layers to determine what protocol/application message was received.

At minimum, preserve:

* Source/module identifier where applicable
* Message identifier
* Reconstructed payload
* Relevant transport metadata

The transport layer must not interpret fields such as:

```text
SN
FW
counter
temperature
voltage
fault code
```

Those belong to protocol/application layers.

---

### 6. Multi-context diagnostic reassembly

The challenge contains diagnostic messages from four independent modules.

The transport implementation must maintain independent reassembly state for each active module/context.

Do not use one global reassembly buffer.

Conceptually:

```text
Module 0 → Reassembly Context 0
Module 1 → Reassembly Context 1
Module 2 → Reassembly Context 2
Module 3 → Reassembly Context 3
```

Frames belonging to different modules may be interleaved.

For example:

```text
Module 0 → FF
Module 1 → FF
Module 2 → FF
Module 3 → FF
Module 0 → CF
Module 2 → CF
Module 1 → CF
Module 3 → CF
...
```

The implementation must reconstruct each message independently.

A single sequential receive loop is sufficient. Threads are not required to achieve transport-level concurrency.

---

### 7. First Frame handling

When a valid First Frame is received:

* Extract the declared message length.
* Reject messages larger than the challenge maximum of `64` bytes.
* Create or replace the corresponding reassembly context.
* Store the payload already contained in the First Frame.
* Initialize the expected sequence number for subsequent Consecutive Frames.

If a new First Frame arrives for a context that already contains an unfinished message, the previous message must be abandoned and the new message must become the active context.

The old buffer must no longer be retained.

---

### 8. Consecutive Frame handling

A Consecutive Frame must only be accepted when an active reassembly context exists for its module.

If no active context exists:

```text
orphan CF → ignore
```

The sequence number must match the expected sequence number.

If the sequence number is incorrect:

```text
sequence error → abandon current message
```

The abandoned context must be cleared so that stale data cannot be combined with a future message.

Sequence numbers must correctly handle the protocol's sequence-number wraparound.

---

### 9. Message completion

A diagnostic message is complete when the accumulated payload length reaches the declared message length.

After successful completion:

1. Create the complete message.
2. Notify the registered transport listener.
3. Clear the reassembly context.
4. Ensure the completed payload is no longer retained unnecessarily.

The completion timestamp required by the grader must be captured by the appropriate upper layer when the complete message is delivered.

The transport layer must not print or emit grader NDJSON directly.

---

### 10. Bounded memory

Reassembly state must remain bounded.

The implementation must:

* Reject oversized messages.
* Limit each context to the configured maximum payload size.
* Clear abandoned contexts.
* Clear completed contexts.
* Avoid retaining references to abandoned payload buffers.
* Avoid creating unbounded collections of incomplete messages.

The maximum diagnostic payload for this challenge is:

```text
64 bytes
```

Repeated malformed or abandoned messages must not cause memory usage to grow without bound.

---

### 11. Listener / notification mechanism

The transport layer should expose a lightweight listener mechanism.

Conceptually:

```text
Transport
    │
    │ complete message
    ▼
TransportListener
```

The transport must notify listeners only after a complete message has been successfully reconstructed.

The listener interface must remain independent from:

* Terminal output
* Grader output
* Telemetry decoding
* Fault decoding
* Diagnostic string parsing

The listener should receive a structured complete-message object rather than raw CAN frames.

---

### 12. Noise handling

The communication layer may receive unrelated CAN traffic.

The implementation must not treat unrelated frames as diagnostic payloads.

Noise frames from the challenge range:

```text
0x200–0x2FF
```

must not contribute to:

```text
frames_processed
```

The transport layer should ignore frames that do not belong to a supported transport message.

Application-level frame accounting will be handled by the appropriate upper layer.

---

### 13. Error handling

Expected malformed transport situations must be handled as normal runtime conditions.

Do not terminate the application because of:

* Orphan Consecutive Frames
* Restarting First Frames
* Oversized messages
* Sequence errors
* Incomplete messages
* Invalid transport state

Avoid broad exception handling such as:

```python
except Exception:
    pass
```

Errors that represent actual communication failures should remain distinguishable from malformed protocol traffic.

---

### 14. Configuration

Do not hard-code runtime configuration inside the communication implementation.

The architecture should allow configuration of values such as:

* CAN interface
* Maximum diagnostic payload length
* Number of supported module contexts
* Receive buffer configuration where applicable
* Debug/logging behavior

Protocol constants should remain separate from runtime settings where practical.

---

### 15. Logging and output

The communication and transport layers must not write application output directly to stdout.

In particular, they must not emit grader NDJSON.

If diagnostic/debug logging is required, it must be routed through the project's logging/output mechanism and must not corrupt grader stdout.

The grader mode requirement is:

```text
stdout → NDJSON only
stderr → diagnostics/logging
```

How to enable debug logging, the catalog of debug lines emitted by this feature, and how to read them against the generator are documented in [`./docs/debug-mode.md`](/docs/debug-mode.md).

---

## Expected Project Structure

After implementing this feature, the relevant structure should be approximately:

```text
src/
├── communication/
│   ├── __init__.py
│   ├── interface.py
│   ├── frame.py
│   └── socketcan.py
│
├── transport/
│   ├── __init__.py
│   ├── transport.py
│   ├── reassembler.py
│   └── listener.py
│
├── models/
│   ├── __init__.py
│   ├── can_frame.py
│   └── message.py
│
└── config/
    ├── __init__.py
    ├── settings.py
    └── constants.py
```

The exact file organization may be adjusted if the existing project structure provides a better fit, but the architectural responsibilities must remain separated.

---

## Testing Requirements

Add tests for the transport behavior without requiring transmission on a real CAN interface.

At minimum, cover:

* Valid CAN frame parsing
* Valid First Frame
* Valid Consecutive Frame
* Complete message reconstruction
* Multiple independent reassembly contexts
* Interleaved module traffic
* Orphan Consecutive Frame
* Restarting First Frame
* Oversized message
* Out-of-order sequence
* Sequence number wraparound
* Context cleanup after completion
* Context cleanup after abandonment
* Repeated abandonment without unbounded state growth

Tests must not transmit CAN frames as part of the application implementation.

Where possible, transport tests should operate on constructed `CANFrame` objects so protocol behavior can be tested independently from SocketCAN.

---

## Check when done

### Architecture

* Communication is separated from transport.
* SocketCAN-specific code is isolated from protocol/application logic.
* Transport does not decode telemetry, fault, or diagnostic payload semantics.
* No global Singleton is introduced.
* Dependencies are composed explicitly.

### Communication

* `vcan0` can be opened successfully.
* CAN frames are received through Python's standard-library SocketCAN API.
* No CAN frames are transmitted.
* No prohibited CAN libraries are used.

### Transport

* Valid multi-frame messages are reconstructed correctly.
* Multiple module contexts can be active simultaneously.
* Interleaved diagnostic traffic is handled correctly.
* Orphan CFs are ignored.
* Restarting FFs replace unfinished contexts.
* Messages larger than 64 bytes are rejected.
* Sequence errors abandon the affected context.
* Sequence-number wraparound is handled correctly.
* Completed and abandoned contexts are released.

### Memory

* Reassembly buffers are bounded.
* Repeated malformed/abandoned messages do not cause unbounded state growth.

### Testing

* Unit tests cover normal and malformed transport sequences.
* Tests cover interleaved messages from multiple modules.
* Tests do not require CAN transmission.

### Code quality

* Python standard library only.
* Clear type hints and data models are used where appropriate.
* No magic protocol values are scattered through the implementation.
* No broad exception swallowing.
* No application output is printed directly by communication/transport components.
* Existing project documentation and architecture remain consistent.
