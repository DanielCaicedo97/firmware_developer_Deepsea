# Architecture Context

## 1. Purpose

The DeepSea Diagnostic Tool is designed as a layered and transport-agnostic diagnostic system.

The current challenge uses a Linux virtual CAN interface (`vcan0`) through SocketCAN. However, the application architecture should not depend directly on CAN-specific communication mechanisms.

The main architectural goal is to separate:

* Physical or communication transport
* Message reception
* Transport-level processing
* Message routing
* Protocol decoding
* Application validation
* Output and presentation

This allows the system to evolve from the current CAN-based implementation to other communication mechanisms such as UART, SPI, or a physical CAN interface without redesigning the application layers above the transport boundary.

---

# 2. Architectural Principles

The architecture follows these principles:

### Transport independence

Upper layers should not depend directly on CAN, UART, SPI, or any other physical communication mechanism.

### Dependency inversion

Higher-level components depend on communication abstractions rather than concrete transport implementations.

### Single responsibility

Each layer should have one clear responsibility.

### Explicit state

Protocol state and reassembly state must be explicit and independently owned.

### Bounded resources

Buffers, contexts, listeners, and other resources must have predictable limits.

### Receive-only operation

For the current challenge, the communication path is strictly receive-only.

### Deterministic processing

The same input sequence must produce the same decoded result and state transitions.

---

# 3. High-Level Architecture

The system follows this general flow:

```text
Communication Interface
          │
          ▼
      Transport
          │
          ▼
   Complete Message
          │
          ▼
        Router
       ┌──┼───────┐
       │  │       │
       ▼  ▼       ▼
 Telemetry Fault Diagnostic
       │  │       │
       └──┼───────┘
          ▼
      Controller
          │
          ▼
       Services
          │
       ┌──┴─────────┐
       ▼            ▼
 Normal Mode    Grader Mode
```

The important boundary is:

```text
Communication
      │
      ▼
Transport
      │
      ▼
Application Message
```

Everything above this boundary should remain independent from the underlying communication mechanism whenever possible.

---

# 4. Communication Abstraction

The communication layer provides the capability to receive raw frames or packets.

It should expose a generic interface rather than a CAN-specific API.

Conceptually:

```text
                  CommunicationInterface
                         <<interface>>
                               │
               ┌───────────────┼───────────────┐
               │               │               │
               ▼               ▼               ▼
           SocketCAN          UART             SPI
            (CAN)          implementation   implementation
```

The current project only implements SocketCAN.

Future implementations may provide the same communication capability through other transports.

The upper layers should interact with the abstraction rather than directly creating sockets or accessing hardware-specific APIs.

---

# 5. Transport Implementations

## 5.1 Current Implementation

The current implementation uses:

```text
Application
     │
     ▼
Communication Interface
     │
     ▼
SocketCAN
     │
     ▼
vcan0
```

`vcan0` is used because the challenge provides a simulated CAN environment.

The architecture must not assume that `vcan0` is permanent.

The same implementation should conceptually support:

```text
vcan0
can0
```

where the underlying communication mechanism remains SocketCAN.

---

## 5.2 Future Transport Implementations

The architecture should allow future communication implementations such as:

```text
CommunicationInterface
│
├── SocketCanInterface
│
├── UartInterface
│
├── SpiInterface
│
└── OtherInterface
```

The application should not require changes to its routing, controllers, or services when a new communication implementation is introduced.

---

# 6. Dependency Direction

Dependencies should flow from higher-level policy toward abstractions.

```text
┌─────────────────────────────┐
│          Services           │
└──────────────┬──────────────┘
               │
┌──────────────▼──────────────┐
│         Controller          │
└──────────────┬──────────────┘
               │
┌──────────────▼──────────────┐
│           Router            │
└──────────────┬──────────────┘
               │
┌──────────────▼──────────────┐
│         Transport           │
└──────────────┬──────────────┘
               │
               ▼
      Communication Interface
               ▲
               │
      ┌────────┴────────┐
      │                 │
 SocketCAN            UART
```

The important point is that the application depends on the **interface**, while concrete communication implementations satisfy that interface.

---

# 7. Communication Interface Responsibilities

The communication abstraction should be intentionally small.

Its responsibilities are limited to communication operations such as:

* Opening the communication channel
* Receiving data
* Reporting communication errors
* Closing the communication channel

It should not know about:

* Telemetry
* Faults
* Diagnostic messages
* Module state
* Application-level validation
* Grader output
* Dashboard rendering

For example:

```text
CommunicationInterface

    start()
       │
       ▼
    receive()
       │
       ▼
    stop()
```

The interface should not contain application protocol logic.

---

# 8. CAN Implementation

The CAN implementation is responsible for adapting SocketCAN to the generic communication interface.

Conceptually:

```text
SocketCAN
    │
    ▼
SocketCanInterface
    │
    ▼
CommunicationInterface
```

Its responsibilities include:

* Creating the SocketCAN socket
* Binding to the configured interface
* Receiving CAN frames
* Converting raw socket data into the application's frame representation
* Handling communication-level errors
* Closing the socket

It should not:

* Decode telemetry
* Decode faults
* Reassemble diagnostic messages
* Route application messages
* Produce grader output

---

# 9. CAN Frame Representation

The raw CAN representation should be isolated from the rest of the application.

Conceptually:

```text
Raw Socket Data
       │
       ▼
CAN Frame
       │
       ├── Identifier
       ├── Data
       └── Length
```

The frame representation provides a clean object for the Transport layer.

For example:

```text
CanFrame
├── can_id
├── data
└── length
```

The rest of the application should not need to understand the binary layout returned directly by the Python socket.

---

# 10. Receive Buffer

The communication layer may receive multiple units (frames, packets or byte chunks) before higher-level processing consumes them.

The architecture therefore places an application-owned receive buffer between communication and transport processing. It is a first-class component, not an optimization: it is the decoupling point that lets any communication implementation feed any transport.

```text
Communication Interface      (producer: SocketCAN, UART, SPI, ...)
          │
          ▼
     Receive Buffer           (bounded FIFO, protocol-agnostic)
          │
          ▼
       Transport              (consumer)
```

## 10.1 Buffering Layers

On a real system there are several buffers below ours. Each has its own owner and policy:

```text
Physical bus / line
      │
      ▼
Hardware RX FIFO / mailbox   (CAN controller, UART FIFO, SPI DMA)
      │
      ▼
Driver / kernel queue        (SocketCAN socket queue, tty buffer, spidev)
      │
      ▼
Application Receive Buffer   (this component)
```

The application buffer is the only one the application controls on every platform. It represents the application's buffering policy and must not be confused with the hardware mailbox or the kernel socket buffer. On `vcan0` it emulates the behavior of a small RX mailbox; on `can0`, UART or SPI it sits on top of the real one unchanged.

## 10.2 Contract

* **Generic element type.** The buffer stores whatever the communication interface produces (`CanFrame` for SocketCAN, raw byte chunks for UART/SPI). It never inspects content.
* **Bounded.** Capacity is `RX_BUFFER_SIZE`, from configuration. Memory use is fixed regardless of bus load.
* **FIFO.** Arrival order is preserved; transport state machines depend on it.
* **Explicit overflow policy.** When full, the newest unit is dropped (the same behavior as a hardware RX FIFO overrun) and an `rx_overflows` counter is incremented and reported on stderr. Overflow is never silent.
* **Single producer, single consumer.** The communication interface pushes, the transport pops.

## 10.3 Execution Model

For the current challenge, producer and consumer run in the same single-threaded loop:

```text
loop:
    interface.receive_into(buffer)   # drain available units, up to capacity, with a short timeout
    while buffer not empty:
        transport.process(buffer.pop())
    periodic tasks (stats, dashboard refresh)
```

Because the buffer is the contract between the layers, the producer can later move to a dedicated reader thread (a thread-safe bounded queue, e.g. `queue.Queue(maxsize=...)`) or be driven by hardware interrupts, without changing the transport or anything above it.

## 10.4 Why It Matters

* A slow consumer (dashboard redraw, a blocked stdout pipe in grader mode) is absorbed by a buffer the application controls and monitors, instead of turning into silent drops in a lower layer.
* Byte-stream transports (UART, SPI) need a buffer anyway, because framing happens over a stream of chunks, not individual frames.
* Overflow is measurable (`rx_overflows`), so buffer size can be tuned with data rather than guessed.

---

# 11. Transport Layer

The Transport layer converts buffered units into complete application-level messages.

```text
Buffered unit (frame / byte chunk)
    │
    ▼
Transport
    │
    ├── Validate unit
    ├── Identify transport state (per source)
    ├── Manage reassembly / framing
    └── Produce complete message
             │
             ▼
       Complete Message
```

The Transport layer should not determine whether a message is:

* Telemetry
* Fault
* Diagnostic

That decision belongs to the Router.

This separation is intentional.

## 11.1 One Transport Per Communication Protocol

Each communication protocol has its own transport implementation behind a common interface. Each one knows how messages are framed on its medium, nothing more.

```text
                      Transport
                    <<interface>>
                          │
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                 ▼
   CanTransport      UartTransport     SpiTransport
 (single-frame +    (delimiter or      (fixed-size or
  ISO 15765-2-style  length-prefixed     length-prefixed
  segmentation)      framing)            framing)
```

Only `CanTransport` is implemented for the challenge.

## 11.2 Framing Is Configuration, Not Meaning

On CAN, some identifiers carry single-frame messages and others carry segmented ones. The transport must know *how* each source is framed in order to reassemble, but not *what* it carries.

This is resolved through configuration injected at composition time:

```text
CanTransport framing map
├── 0x100–0x103, 0x1F0 → single-frame  (one frame = one complete message)
└── 0x6F0–0x6F3        → segmented     (FF/CF reassembly, one context per ID)
```

The transport only answers "how is this source framed?". The Router still decides what the resulting message is. Adding a new segmented source, or moving to another bus, changes configuration or the transport implementation, never the Router, protocol handlers or controller.

## 11.3 Output

Every transport produces the same message object, independent of the medium:

```text
Message
├── message_id  (what was received: the CAN ID on CAN)
├── source_id   (transport source/context; equals the CAN ID on this bus)
├── payload     (bytes, complete, never interpreted by the transport)
└── metadata
    ├── framing         (single_frame | segmented)
    ├── frame_count     (frames that made up the message)
    └── received_at_ns  (monotonic ns of the frame that completed it, captured at the communication boundary)
```

This `Message` is the boundary described in §3: everything above it is protocol-agnostic.

The grader `ts_ns` (completion timestamp) is **not** taken by the transport. Per feature spec 01 §9, the upper layer captures `time.monotonic_ns()` when the complete message is delivered to it.

## 11.4 Frame Outcome

`Transport.process(unit)` returns a `FrameOutcome` (`IGNORED`, `ACCEPTED`, `COMPLETED`, `REJECTED`). `IGNORED` means the unit is not on a supported source (e.g. noise `0x200`–`0x2FF`); every other value means the unit was on a real source. Upper layers use this for `frames_processed` accounting, so rejected diagnostic frames are counted and noise never is, without the transport owning any statistics.

## 11.5 Reassembly Rules As Implemented

* Contexts are created once at construction, one per segmented source in the framing map, and reset in place. Their number never changes at runtime.
* **Any** First Frame on a source ends the previous attempt on that source, even if the new First Frame is then rejected (oversized, declared length < 8, DLC < 8).
* First Frames declaring fewer than 8 bytes are rejected: CHALLENGE.md states messages are always longer than 7 bytes (no Single Frame case).
* Consecutive Frames on an idle context are orphans and are ignored, leaving the context untouched.
* A wrong sequence nibble, or a Consecutive Frame with no data, abandons the attempt.
* Sequence nibbles go 1…15, 0, 1…; bytes beyond the declared length (final-frame padding) are discarded.
* Other PCI types (Single Frame, Flow Control) are rejected without touching the context.

---

# 12. Transport vs Protocol

The distinction between Transport and Protocol is fundamental.

### Transport

Answers:

> How do I obtain a complete message from one or more received frames?

### Protocol

Answers:

> What does this complete message mean?

Therefore:

```text
CAN Frames
    │
    ▼
Transport
    │
    ▼
Complete Message
    │
    ▼
Protocol
```

This prevents CAN-specific transport details from leaking into application-level protocol handling.

---

# 13. Diagnostic Reassembly

Diagnostic messages may span multiple CAN frames.

The Transport layer manages the reassembly state.

Each module must have an independent context.

```text
Transport
    │
    ├── Module 0 → Reassembly Context
    ├── Module 1 → Reassembly Context
    ├── Module 2 → Reassembly Context
    └── Module 3 → Reassembly Context
```

This allows interleaved messages to be processed independently.

Example:

```text
Module 0 → First Frame
Module 1 → First Frame
Module 2 → First Frame
Module 3 → First Frame

Module 0 → Consecutive Frame
Module 2 → Consecutive Frame
Module 1 → Consecutive Frame
Module 3 → Consecutive Frame
```

Each context maintains its own state.

A single global reassembly buffer must not be used for all modules.

---

# 14. Reassembly State

A diagnostic context may contain information such as:

```text
DiagnosticContext
├── active
├── source identifier
├── expected length
├── received length
├── expected sequence
└── payload buffer
```

The implementation should only retain state required to process the current message.

When a message:

* Completes
* Becomes invalid
* Is abandoned
* Is replaced by a new First Frame

the corresponding context must be reset.

---

# 15. Message Completion

Once Transport has reconstructed a complete message:

```text
Frames
  │
  ▼
Transport
  │
  ▼
Complete Message
```

the Transport layer notifies the next layer.

Conceptually:

```text
TransportListener
        │
        ▼
on_message(message)
```

This creates a clean boundary between Transport and the application.

---

# 16. Observer / Listener Pattern

The Transport layer may use a lightweight listener mechanism.

```text
                    Transport
                        │
                        │ notify(message)
                        ▼
                TransportListener
                        │
                        ▼
                      Router
```

The listener should receive a complete message rather than individual transport frames.

This prevents upper layers from becoming dependent on reassembly details.

The Observer mechanism should remain simple.

There is no need for a complex event framework.

---

# 17. Router

The Router is responsible for classifying complete messages.

```text
                 Complete Message
                        │
                        ▼
                     Router
                  ┌─────┼─────┐
                  │     │     │
                  ▼     ▼     ▼
             Telemetry Fault Diagnostic
```

The Router determines which protocol handler should process the message.

For the current challenge, classification is based primarily on CAN identifiers.

The Router should not contain detailed decoding logic.

---

# 18. Protocol Handlers

Each protocol should have its own handler.

```text
protocol/
│
├── telemetry.py
├── fault.py
└── diagnostic.py
```

### Telemetry Handler

Responsible for:

* Validating telemetry messages
* Decoding telemetry fields
* Producing telemetry data

### Fault Handler

Responsible for:

* Validating fault messages
* Decoding fault information
* Producing fault data

### Diagnostic Handler

Responsible for:

* Validating diagnostic messages
* Interpreting completed diagnostic payloads
* Producing diagnostic information

Each handler should focus on its own protocol.

---

# 19. Controller

The Controller coordinates application-level behavior after protocol decoding.

```text
Protocol Handler
       │
       ▼
   Controller
       │
       ├── Validate application data
       ├── Update module state
       └── Generate application events
```

The Controller should not know how data is displayed or serialized.

For example, it should not contain:

```python
print(...)
json.dumps(...)
```

as part of its core business logic.

---

# 20. Application State

The system may maintain an application-level representation of the four power modules.

Conceptually:

```text
Application State
│
├── Module 0
├── Module 1
├── Module 2
└── Module 3
```

Each module may contain:

* Latest telemetry
* Latest sequence
* Fault state
* Diagnostic information
* Other application-level status

This state is separate from Transport reassembly state.

---

# 21. Services

Services consume application-level information and provide external behavior.

```text
Controller
     │
     ▼
 Services
     │
     ├── Normal Output
     ├── Grader Output
     └── Statistics
```

The service layer should not perform low-level CAN decoding.

---

# 22. Output Modes

The application supports two primary output modes.

## Normal Mode

Designed for human operators.

Possible output includes:

* Module status
* Telemetry
* Fault information
* Diagnostic messages
* Statistics

## Grader Mode

Designed for automated evaluation.

Output must follow the challenge-defined NDJSON format.

```text
stdout
  └── NDJSON events

stderr
  └── Diagnostic/logging information
```

The underlying application state and protocol processing should remain identical between both modes.

Only the presentation/output strategy changes.

---

# 23. Configuration

Runtime and operational configuration should be centralized.

A configuration module should provide values such as:

```text
config/
└── config.py
```

or, when separating constants from runtime configuration:

```text
config/
├── constants.py
└── settings.py
```

Configuration may include:

### Communication

```text
CAN interface
RX buffer size
Receive timeout
```

### Application

```text
Number of modules
Diagnostic buffer limits
Maximum diagnostic message length
```

### Output

```text
Normal mode
Grader mode
Debug mode
```

### Logging

```text
Debug enabled
Log level
```

### Storage

```text
Output path
Diagnostic file path
Statistics path
```

Configuration values should not be scattered throughout the codebase.

---

# 24. Configuration Example

Conceptually:

```text
ApplicationConfig
│
├── communication
│   ├── interface
│   ├── rx_buffer_size
│   └── timeout
│
├── protocol
│   ├── module_count
│   └── max_diagnostic_length
│
├── output
│   ├── mode
│   └── output_path
│
└── logging
    ├── debug
    └── level
```

Example configuration:

```python
@dataclass
class CommunicationConfig:
    interface: str
    rx_buffer_size: int
    timeout: float
```

This keeps configuration explicit and testable.

---

# 25. Debug Mode

Debug output should be controlled through configuration.

For example:

```text
debug = false
```

When enabled, diagnostic information may be written to stderr.

Debug output must never corrupt grader output.

Therefore:

```text
Debug
  │
  └── stderr
```

while:

```text
Grader events
  │
  └── stdout
```

This separation is mandatory in grader mode.

---

# 26. Storage and File Paths

File paths should be configurable rather than hard-coded throughout the application.

Example:

```text
output_path
diagnostic_output_path
log_path
```

Services responsible for persistence should receive the configured paths.

Protocol handlers and controllers should not need to know where files are stored.

---

# 27. Dependency Injection

Dependencies should be provided to components rather than created internally whenever practical.

For example:

```text
main.py
   │
   ├── creates CommunicationInterface
   │
   ├── creates Transport
   │
   ├── creates Router
   │
   ├── creates Controller
   │
   └── creates Output Service
```

Conceptually:

```text
main.py
   │
   ▼
Dependency Composition
   │
   ▼
Application
```

This makes components easier to:

* Test
* Replace
* Configure
* Reuse

---

# 28. Single Communication Instance

Although the current system communicates with a single CAN interface, a traditional Singleton implementation is not required.

The architecture should instead create one communication instance at the application composition level.

```text
main.py
   │
   ▼
SocketCanInterface
   │
   └── single application instance
```

This provides a single owner of the physical/logical communication resource without introducing hidden global state.

This approach also allows tests to inject a fake implementation:

```text
Production
    └── SocketCanInterface

Testing
    └── FakeCanInterface
```

---

# 29. Concurrency Model

The architecture supports multiple active protocol contexts without requiring multiple threads.

The CAN receive loop may process frames sequentially:

```text
Frame 1
  ↓
Frame 2
  ↓
Frame 3
  ↓
Frame 4
```

while maintaining independent state:

```text
Module 0 context
Module 1 context
Module 2 context
Module 3 context
```

Therefore:

> **Sequential frame processing + independent protocol state provides logical concurrency without unnecessary threading.**

This is preferred for the current challenge because it provides:

* Deterministic behavior
* Simpler synchronization
* Lower complexity
* Easier testing
* Easier static analysis

---

# 30. Proposed Project Structure

The architecture can be represented in the project as:

```text
deepsea-can-diagnostic/
│
├── App/
│   ├── src/                    (source root; imports are `from transport... import`)
│   │   │
│   │   ├── main.py             (entry point)
│   │   │
│   │   ├── communication/
│   │   │   ├── __init__.py
│   │   │   ├── interface.py
│   │   │   ├── frame.py            (raw struct can_frame → CanFrame)
│   │   │   ├── rx_buffer.py        (not yet implemented)
│   │   │   └── socketcan.py
│   │   │
│   │   ├── transport/
│   │   │   ├── __init__.py
│   │   │   ├── transport.py        (Transport interface)
│   │   │   ├── can_transport.py    (single-frame + segmented framing map)
│   │   │   ├── reassembler.py
│   │   │   └── listener.py
│   │   │
│   │   ├── protocol/
│   │   │   ├── __init__.py
│   │   │   ├── router.py
│   │   │   ├── telemetry.py
│   │   │   ├── fault.py
│   │   │   └── diagnostic.py
│   │   │
│   │   ├── controller/
│   │   │   ├── __init__.py
│   │   │   └── controller.py
│   │   │
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── output.py
│   │   │   ├── dashboard.py
│   │   │   └── grader.py
│   │   │
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── can_frame.py
│   │   │   ├── message.py
│   │   │   ├── telemetry.py
│   │   │   ├── fault.py
│   │   │   └── diagnostic.py
│   │   │
│   │   └── config/
│   │       ├── __init__.py
│   │       ├── settings.py
│   │       └── constants.py
│   │
│   └── test/                   (unittest; top-level dir for discovery, not a package)
│       ├── helpers.py          (frame builders, FakeCanSocket, RecordingListener)
│       ├── unit/               (one component in isolation)
│       │   ├── communication/
│       │   ├── transport/
│       │   ├── models/
│       │   └── config/
│       ├── integration/        (layers wired across a boundary, fake socket)
│       │   └── communication_transport/
│       └── e2e/                (live vcan0 + challenge generator; skipped off the Pi)
│           └── live_bus/
│
├── docs/
│   ├── PROJECT_OVERVIEW.md
│   ├── CODE_STANDARDS.md
│   └── architecture-context.md
│
├── README.md
├── .gitignore
└── .gitattributes
```

---

# 31. Data Flow

The complete data flow is:

```text
                  ┌──────────────┐
                  │     vcan0    │
                  └──────┬───────┘
                         │
                         ▼
              ┌────────────────────┐
              │ Communication      │
              │ Interface           │
              └─────────┬──────────┘
                        │
                        ▼
              ┌────────────────────┐
              │ Receive Buffer     │
              └─────────┬──────────┘
                        │
                        ▼
              ┌────────────────────┐
              │ Transport          │
              │                    │
              │ Reassembly         │
              └─────────┬──────────┘
                        │
                        ▼
              ┌────────────────────┐
              │ Complete Message   │
              └─────────┬──────────┘
                        │
                        ▼
              ┌────────────────────┐
              │ Router             │
              └──────┬───┬────┬────┘
                     │   │    │
              ┌──────┘   │    └──────┐
              ▼          ▼           ▼
         Telemetry     Fault     Diagnostic
              │          │           │
              └──────────┼───────────┘
                         ▼
                  ┌──────────────┐
                  │ Controller   │
                  └──────┬───────┘
                         │
                         ▼
                  ┌──────────────┐
                  │   Services   │
                  └──────┬───────┘
                         │
                  ┌──────┴───────┐
                  ▼              ▼
              Dashboard       NDJSON
```

---

# 32. Architectural Boundaries

The following boundaries should remain explicit:

```text
Communication
    │
    │ raw frames
    ▼
Transport
    │
    │ complete messages
    ▼
Protocol
    │
    │ decoded domain data
    ▼
Controller
    │
    │ application state/events
    ▼
Services
    │
    ├── Human output
    └── Machine output
```

Each boundary reduces coupling between components.

---

# 33. What Each Layer Should Not Know

| Layer         | Should know               | Should NOT know           |
| ------------- | ------------------------- | ------------------------- |
| Communication | How to receive data       | Telemetry, faults, grader |
| Transport     | Frame/message assembly    | Dashboard, JSON output    |
| Router        | Message classification    | Socket implementation     |
| Protocol      | Message format            | Output destination        |
| Controller    | Application state         | CAN socket details        |
| Services      | How to present/store data | CAN protocol internals    |
| Configuration | Runtime settings          | Protocol processing       |

This separation is one of the primary architectural goals of the project.

---

# 34. Architectural Goal

The final architecture should make this possible:

```text
                 SAME APPLICATION
                       │
        ┌──────────────┼──────────────┐
        │              │              │
       CAN            UART            SPI
        │              │              │
        └──────────────┼──────────────┘
                       ▼
                   Transport
                       │
                       ▼
                    Router
                       │
            ┌──────────┼──────────┐
            ▼          ▼          ▼
        Telemetry    Fault    Diagnostic
            │          │          │
            └──────────┼──────────┘
                       ▼
                   Controller
                       │
                       ▼
                    Services
```

Only the communication implementation should need to change when the physical transport changes.

The application logic should remain stable.

---

# 35. Design Philosophy

The architecture intentionally combines embedded-systems concepts with Python software design.

The design should preserve useful concepts from embedded development:

* Hardware abstraction
* Peripheral ownership
* Receive buffering
* Message routing
* State machines
* Bounded memory
* Event notification
* Separation between transport and application protocol

while using Python-appropriate mechanisms:

* Interfaces through abstract base classes or protocols
* Dependency injection
* Dataclasses
* Standard-library components
* Explicit object ownership
* Simple listener callbacks
* Deterministic sequential processing

The objective is not to reproduce a C/C++ firmware architecture line by line.

The objective is to preserve the **engineering principles** while implementing them naturally in Python.

---

# 36. Core Architectural Rule

The most important rule of the architecture is:

> **The application should care about messages and their meaning, not about how those messages physically arrived.**

Therefore:

```text
CAN / UART / SPI
       │
       ▼
Communication Abstraction
       │
       ▼
Transport
       │
       ▼
Complete Message
       │
       ▼
Router
       │
       ▼
Application Protocol
```

This keeps the system modular, testable, and extensible while allowing the current implementation to remain focused on the CAN challenge.
