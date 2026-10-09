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
    ├── received_at_ns  (monotonic ns of the frame that completed it, captured at the communication boundary)
    └── completed_at_ns (transport clock, time.monotonic_ns(), read when the message became complete)
```

This `Message` is the boundary described in §3: everything above it is protocol-agnostic.

The grader `ts_ns` (completion timestamp) is `completed_at_ns`. Spec 04 §5.2/§8 requires it to be captured when reassembly completes and preserved through every later layer, so `CanTransport` stamps it with its injectable clock (default `time.monotonic_ns`) as it builds the message. This supersedes spec 01 §9, where the upper layer captured it on delivery. `DiagnosticController` copies it into `DiagnosticCompleteEvent.completed_at_ns` and the grader writes it unchanged. It never reads the clock itself.

## 11.4 Frame Outcome

`Transport.process(unit)` returns a `FrameOutcome` (`IGNORED`, `ACCEPTED`, `COMPLETED`, `REJECTED`). `IGNORED` means the unit is not on a supported source (e.g. noise `0x200`–`0x2FF`); every other value means the unit was on a real source. Upper layers use this for `frames_processed` accounting, so rejected diagnostic frames are counted and noise never is, without the transport owning any statistics.

`Transport.receive_from(communication)` is how the transport consumes frames from the communication layer (spec 04 §5.2). It receives one unit, processes it and returns its `FrameOutcome`, or `None` when the receive timed out. The receive loop calls it through a `functools.partial` built in `main.py`, so the application controller never sees a frame or the communication object.

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

## 17.1 Router As Implemented (Feature 03)

Routing is a two-level hierarchy in the `routes/` package (renamed from `router/` by spec 04), a Python version of the `RootRouter`/`SubRouter` design described in spec 03. It uses only the standard library and no routing framework. Handlers are `ControllerRoute(decoder, controller)` objects: the route decodes, then delegates the result to its domain controller.

```text
Complete Message ──► RootRouter ──(message_id)──► SubRouter ──(message_id)──► handler(message)
                         │                            │
                         └─ no subrouter:             └─ no handler:
                            ROUTE_NOT_FOUND              HANDLER_NOT_FOUND
```

| Module | Contents |
| --- | --- |
| `common/router.py` | `BaseRouter[TargetT]` (per-instance `message_id → target` table and the shared validation), `SubRouter(name, expected_errors=())` (`add_route`, `add_routes`, decorator `@sub.route(*ids)`, `dispatch`, `seal()`/`sealed`), `RootRouter(name="root")` (`include_router`, `dispatch`), `RouteRegistrationError(ValueError)`, `Handler = Callable[[Message], Any]`. Generic: no decoder or controller imports. |
| `common/results.py` | `DispatchStatus` enum and frozen `DispatchResult(status, message, router_name, result, error)` with `succeeded`. |
| `common/controller_route.py` | `ControllerRoute(decoder, controller)`: calls `decoder(message)`, then `controller.handle(result, message)`, and returns the controller's `ControllerResult` (its `decoded` field is the decoder result). A decode error propagates before the controller runs. Also `DECODER_ERRORS = (ProtocolDecodeError,)` and `per_module_ids(base_id)`. |
| `common/__init__.py` | Public API: the generic classes, results and the error. |
| `telemetry/routes.py`, `fault/routes.py`, `diagnostic/routes.py` | `build_<domain>_router(controller, decoder=decode_<domain>) -> SubRouter`. Each registers its domain's IDs with one `ControllerRoute`. |
| `routes_init.py` | `init_routes(telemetry_controller, fault_controller, diagnostic_controller, root=None) -> RootRouter`: composes the three domain routers. |

Challenge routes (`init_routes`):

| Subrouter | Message IDs | Handler |
| --- | --- | --- |
| `telemetry` | `TELEMETRY_BASE_ID` … `+ MODULE_COUNT - 1` (`0x100–0x103`), one `add_routes` call | `decode_telemetry` → `TelemetryController` |
| `fault` | `FAULT_ID` (`0x1F0`) | `decode_fault` → `FaultController` |
| `diagnostic` | `DIAGNOSTIC_BASE_ID` … `+ MODULE_COUNT - 1` (`0x6F0–0x6F3`), one `add_routes` call | `decode_diagnostic` → `DiagnosticController` |
| none | noise `0x200–0x2FF` and every other ID | none: `ROUTE_NOT_FOUND` |

`DispatchStatus`:

* `SUCCESS`: `result` is the handler's return value. For the challenge routes, that is the Feature 02 frozen result (`TelemetryResult`, `FaultResult` or `DiagnosticResult`). There is no second decoding-status model.
* `ROUTE_NOT_FOUND`: the root has no subrouter for the ID. `router_name`, `result` and `error` are `None`.
* `HANDLER_NOT_FOUND`: a subrouter was dispatched for an ID it has no handler for. `router_name` is set. Through the root this cannot happen, because the root only indexes registered IDs. It shows up only when a subrouter is dispatched directly.
* `HANDLER_FAILED`: the handler raised one of its subrouter's `expected_errors`, which is kept in `error`. The challenge subrouters use `expected_errors=(ProtocolDecodeError,)`, so an invalid payload drops one message and the receive loop goes on.

Rules:

* **Registration is explicit and validated.** IDs must be `int` (not `bool`) in `0 … CAN_STANDARD_ID_MASK`, handlers must be callable, and an ID can be registered only once per router. A multi-ID registration is all-or-none. Violations raise `RouteRegistrationError`, and nothing is ever overwritten.
* **Inclusion indexes and seals.** `include_router` registers the subrouter's IDs on the root, all-or-none and rejecting overlaps, then seals the subrouter. A later `add_route` on it raises instead of being silently unreachable, so a subrouter must be fully registered before it is included.
* **Errors.** Only the configured `expected_errors` are caught. Anything else is a programming error and propagates. A subrouter with no `expected_errors` catches nothing.
* **What routers never do.** They read only `message.message_id`. They never parse payloads, reassemble, hold message state, open sockets, log or print.
* **No hidden instances.** There is no module-level router or registry. Each `init_routes()` call builds independent routers, and the entry point will own construction.
* **Not a listener.** The root router is not a `TransportListener`, because `on_message` returns nothing and dispatch has to return its result. `ApplicationController` is the listener: it calls `root.dispatch()` (injected as a callable) and logs any non-`SUCCESS` result at debug level.

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

## 18.1 Decoders As Implemented (Feature 02)

Each decoder is a plain function `decode_x(message: Message) -> XResult` in `protocol/<domain>/decoder.py`. It consumes the Feature 01 `Message` unchanged, and returns a frozen result dataclass from `protocol/<domain>/models.py` (moved out of `models/` by spec 04 §5.3: each domain owns its result models). Each domain package re-exports both, e.g. `from protocol.telemetry import TelemetryResult, decode_telemetry`. On invalid input it raises `protocol.common.ProtocolDecodeError` (a `ValueError`, like `InvalidFrameError`). It never returns a partial or successful result for bad input. The challenge subrouters (§17.1) catch `ProtocolDecodeError` only and report it as `HANDLER_FAILED`, so a bad payload drops one message and the receive loop keeps running. All offsets, scales, masks and text prefixes live in `config/constants.py`.

| Decoder | Accepts | Result | Rejects |
| --- | --- | --- | --- |
| `decode_telemetry` | `TELEMETRY_BASE_ID + module`, 8 bytes `<HHBBH` | `TelemetryResult(module_id, sequence, voltage_v, current_a, temperature_c, enabled, fault, derated)` | ID outside the 4 telemetry IDs, length ≠ 8 |
| `decode_fault` | `FAULT_ID`, 8 bytes | `FaultResult(module_id, code: FaultCode)` | other ID, length ≠ 8, module ≥ `MODULE_COUNT`, code ∉ 1–4, non-zero bytes 2–7 |
| `decode_diagnostic` | `DIAGNOSTIC_BASE_ID + module`, reassembled payload | `DiagnosticResult(message_id, module_id, text, serial_number, firmware_version, counter)` | ID outside the 4 diagnostic IDs, length outside 8–64, non-ASCII or non-printable text, text not `SN:<x> FW:<y>[ #<digits>]` |

Interpretations:

* **Telemetry module** comes from the CAN ID, and **fault module** from payload byte 0, as CHALLENGE.md defines.
* **Scaled values are not rounded** (`voltage_v = raw × 0.1`). Rounding to 2 decimals is an output concern (code standards §16).
* **Undocumented status bits 3–7 are ignored**, not rejected.
* **Identification text format**: the generator sends `f"{DIAG_STRINGS[ctx]} #{counter}"`, and the CHALLENGE.md example shows `SN:… FW:…` with no counter. So `counter` is optional (`None` when absent). `text` keeps the exact received string, because grader `diag_complete.string` must match it byte for byte.

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

## 22.1 Application Layers As Implemented (Feature 04)

Spec 04 (`feature-specs/04-architecture-specification.md`) is implemented as follows. The runtime flow:

```text
SocketCanInterface --receive--> CanTransport.receive_from --FrameOutcome--> ApplicationController.on_frame --> StatsService
                                      |
                                      +-- complete Message --> ApplicationController.on_message --> RootRouter.dispatch
                                                                                                        |
                       SubRouter --> ControllerRoute: decode_<domain>(message) --> <Domain>Controller.handle(result, message)
                                                                                         |
                                                       ApplicationState <-- update ------+
                                                                                         +-- publish(event) --> EventPublisher --on_event--> one EventConsumer
                                                                                                                                       (GraderOutput | Dashboard)
```

**Events** (`models/application_event.py`). This is the one contract between controllers and output. The events are frozen dataclasses, each with a `ClassVar event_type: EventType` whose value is ADAPTER.md's `type`: `TelemetryEvent(telemetry)`, `FaultEvent(fault)`, `DiagnosticCompleteEvent(diagnostic, completed_at_ns)` and `StatsEvent(frames_processed)`. `ApplicationEvent` is their `Union`. Values stay unformatted.

**Controllers** (`controllers/`):

* `BaseController[ResultT]` (Feature 05) takes `ApplicationState`, `StatsService` and an `EventPublisher` by injection, and names its domain with `ClassVar event_type`. Its contract is the abstract `handle(result, message) -> ControllerResult`, called once per successfully decoded message. Each implementation validates the result first. A valid result updates state through `ApplicationState`, publishes one event and is counted with `StatsService.record_processed(event_type)` (`_complete`). An invalid one is counted with `record_rejected`, leaves state and output untouched and returns `REJECTED` with a reason (`_reject`). Service failures (state or publisher raising) are not expected input: they propagate, and nothing is published or counted. The base class has no type-based branching.
* `ControllerResult(status, decoded, event=None, reason=None)` with `ControllerStatus` PROCESSED/REJECTED (`controllers/results.py`) is the explicit processing result. `ControllerRoute` returns it, so it is `DispatchResult.result` for the challenge routes.
* Validation: `TelemetryController` checks that the module is known and that the CAN ID is `TELEMETRY_BASE_ID + module`. `FaultController` checks a known module and a `FaultCode` member. `DiagnosticController` checks for `completed_at_ns` (a message without it is incomplete), a known module, `result.message_id == message.message_id` and non-empty text. It publishes `DiagnosticCompleteEvent` with the transport's `completed_at_ns` and never reads a clock.
* `ApplicationController` is not a `BaseController`: its contract is different. It is the transport's `TransportListener`, and `on_message` dispatches through an injected `dispatch` callable, logs unhandled messages at debug level and controller rejections at warning level (stderr). `on_frame(outcome)` counts every outcome except `IGNORED` and `None`. `report_stats_if_due()` publishes `StatsService.poll(clock())`. `run(poll_frame, keep_running)` is the receive loop: one poll and one stats check per iteration, so stats keep flowing on an idle bus because the receive times out every 0.5 s. `shutdown()` publishes the final stats. It never sees raw frames.

**Services** (`services/`). Feature 06 (`feature-specs/06-services_and_output.md`) completed them:

* `EventPublisher` is a concrete class: `register(consumer)` adds an `EventConsumer` (`on_event(event)`); registering the same consumer twice raises `ValueError`, and a non-consumer raises `TypeError`. `publish(event)` delivers the same event object, synchronously and in registration order, with no queue or thread. **Consumer failure policy:** a consumer raising an `Exception` is logged on stderr, delivery continues to the remaining consumers, and once all have been called `EventDeliveryError(event, failures)` is raised (first exception chained as `__cause__`), so a failure never stops other consumers and is never silent. `KeyboardInterrupt`/`SystemExit` are not caught. This is the only broad `except` in `src/`, and it re-raises. Controllers depend only on `publish`.
* `ApplicationState` holds fixed slots per module: the latest `TelemetryResult`, the current `FaultResult` (`latest_fault`) and the latest diagnostic completion, stored as a `DiagnosticCompleteEvent` so its `completed_at_ns` is kept (`update_identification(result, completed_at_ns)`, `identification`, `diagnostic_completion`). It also keeps a `deque(maxlen=recent_fault_limit)` of recent faults. Every update is validated before commit (expected result type, `int` module in range, `FaultCode` member, identification ID `DIAGNOSTIC_BASE_ID + module`, non-empty text, non-negative `int` timestamp), so an invalid update raises and the last valid state stays. `snapshot()` returns a frozen `StateSnapshot` of tuples. No internal collection is exposed, and nothing grows with traffic.
* `StatsService(report_interval_ns)` owns `frames_processed` (`record_frame()`), fixed per-domain counters (`record_processed`/`record_rejected`/`processed`/`rejected`, keyed by the telemetry, fault and diag_complete `EventType`s), `snapshot()` (a frozen `StatsSnapshot` with read-only mapping copies), `stats_event()` (the ADAPTER.md `StatsEvent`, `frames_processed` only) and `poll(now_ns)` (the first poll reports, then one report per interval).
* **Single counting point for `frames_processed`:** `ApplicationController.on_frame` is the only caller of `record_frame`, once per received frame whose `FrameOutcome` is not `IGNORED`. The transport's framing map holds exactly 0x100–0x103, 0x1F0 and 0x6F0–0x6F3, so noise (0x200–0x2FF) is never counted. A diagnostic frame counts once even if its message is later abandoned, and completed messages, decoders and controllers never count frames.

**Output** (`output/`). Both adapters implement `EventConsumer`. `main.build_output` picks exactly one per run, and it is the only consumer registered with the `EventPublisher`:

* `GraderOutput(stream)` writes one line per event (`to_json_line`: `json.dumps(..., allow_nan=False)`, so a NaN/infinity raises instead of producing invalid JSON, and nothing is written for it) and flushes each one. Fields are ADAPTER.md's flat objects with a `type` field. The `event`/`data` shape in spec 06 §6.2 is explicitly a placeholder and is not used. `voltage` and `current` are rounded to 2 decimals, `temp_c` is an int, `can_id` is `f"{id:#x}"`, `string` is the exact received text and `ts_ns` is `completed_at_ns` unchanged.
* `Dashboard(state, stream, refresh_interval_ns)` redraws in place with ANSI `ESC[H` / `ESC[K` / `ESC[J` (no curses). Events only trigger redraws, and the values come from one `ApplicationState.snapshot()` per redraw, so nothing is decoded. Stats events always redraw; other events redraw at most once per refresh interval. The final stats event at shutdown draws the final state. `format_dashboard(snapshot, frames_processed)` is pure and shows placeholders for missing data.

**Composition and lifecycle** (`main.py`):

1. Parse `--iface`, `--grader` and `--debug`, then `build_application_config` (adds `OutputConfig(mode, stats_interval_s, dashboard_refresh_s, recent_fault_limit)`).
2. Build `SocketCanInterface`, then `CanTransport`.
3. `build_application` builds the state, `StatsService`, one `EventPublisher` with the mode's single output consumer registered (`build_output`), the three controllers, `init_routes(...)` and `ApplicationController`, and adds the latter as the transport listener.
4. `run`: open the bus, install a SIGTERM handler (`ShutdownRequest`) that stops the loop after the current receive, and run until Ctrl+C or SIGTERM. Then `stop()` publishes the final stats and closes the socket in `finally`. The socket is closed even if the final stats cannot be delivered (logged). A `CommunicationError` or `EventDeliveryError` exits with code 1, logged on stderr; stdout gets nothing but output events.

**Dependency rules (checked by grep):** `communication` imports no controllers, routes or output. `transport` imports `communication.interface` but no output. `protocol` imports no controllers, output, routes or services. `controllers` import `routes.common.results` (a contract) but no domain routes or `routes_init`. `services` import no output. `output` imports `services` and `models` but no decoders, transport or communication. `models/application_event.py` imports only the protocol result models. Every module imports on its own with no cycles.

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

The project structure, as implemented after spec 04. `App/src/` is the source root, and `main.py` is the composition root:

```text
deepsea-can-diagnostic/
│
├── App/
│   ├── src/                    (source root; imports are `from transport... import`)
│   │   ├── main.py             (composition root and lifecycle, §22.1)
│   │   │
│   │   ├── communication/      interface.py, frame.py (raw struct can_frame → CANFrame), socketcan.py
│   │   │                       (rx_buffer.py not yet implemented)
│   │   ├── transport/          transport.py (Transport, FrameOutcome, receive_from), can_transport.py,
│   │   │                       reassembler.py, listener.py
│   │   ├── protocol/
│   │   │   ├── common/         __init__.py (ProtocolDecodeError, shared validation)
│   │   │   ├── telemetry/      decoder.py, models.py (TelemetryResult)
│   │   │   ├── fault/          decoder.py, models.py (FaultCode, FaultResult)
│   │   │   └── diagnostic/     decoder.py, models.py (DiagnosticResult)
│   │   ├── routes/
│   │   │   ├── common/         router.py (Base/Sub/RootRouter), results.py, controller_route.py
│   │   │   ├── telemetry/      routes.py
│   │   │   ├── fault/          routes.py
│   │   │   ├── diagnostic/     routes.py
│   │   │   └── routes_init.py
│   │   ├── controllers/
│   │   │   ├── base_controller.py
│   │   │   ├── results.py      ControllerStatus, ControllerResult
│   │   │   ├── application_controller.py
│   │   │   ├── telemetry/      telemetry_controller.py
│   │   │   ├── fault/          fault_controller.py
│   │   │   └── diagnostic/     diagnostic_controller.py
│   │   ├── services/           event_publisher.py, application_state.py, stats_service.py
│   │   ├── output/             dashboard.py, grader.py
│   │   ├── models/             can_frame.py, message.py, application_event.py
│   │   └── config/             constants.py, settings.py
│   │
│   └── test/                   (unittest; top-level dir for discovery, not a package)
│       ├── helpers.py          (frame/message builders, FakeCanSocket, RecordingListener,
│       │                        RecordingPublisher, RecordingController, FakeClock)
│       ├── unit/               communication/, transport/, models/, config/, protocol/, routes/,
│       │                       controllers/, services/, output/
│       ├── integration/        communication_transport/, transport_protocol/,
│       │                       application/ (main.build_application + main.run, both modes)
│       └── e2e/live_bus/       (live vcan0 + challenge generator; skipped off the Pi)
│
├── Context/                    (specs and context files)
├── docs/
├── README.md
├── .gitignore
└── .gitattributes
```

Differences from spec 04 §4's logical tree, kept on purpose (§10: "do not rewrite functioning … logic solely to match a preferred filename"):

* Code lives under `App/src/`, and `main.py` sits there, not at the repo root (user decision, see the progress tracker).
* `transport/can_transport.py` is kept next to the `transport.py` interface (§11.1).
* `models/can_frame.py` is kept, because the frame model is shared by communication and transport.
* `routes/common/controller_route.py` is an extra module. It holds the decoder → controller handler shared by the three domain routes, which keeps `router.py` free of controller imports.
* Tests stay organised type first (`unit/`, `integration/`, `e2e/`), then by area (user decision), not `tests/<layer>/`.

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
