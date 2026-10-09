# Feature 05 — Controllers

## 1. Objective

Implement `BaseController` and the concrete controllers for telemetry, faults, and diagnostics, using the interfaces established by the communication, transport, protocol, and routing layers.

Controllers coordinate application behavior after a message has been routed. They must remain independent of the CAN interface, frame reception, transport reassembly, terminal rendering, and grader formatting.

## 2. Scope

### Included

* Define a small `BaseController` contract.
* Implement `TelemetryController`.
* Implement `FaultController`.
* Implement `DiagnosticController`.
* Integrate the controllers with the router and application services.
* Validate decoded results before updating application state.
* Add unit tests for successful processing, invalid results, and service interactions.

### Excluded

* Reading frames from SocketCAN.
* Reassembling diagnostic transport messages.
* Implementing protocol decoding.
* Directly printing events to `stdout`.
* Implementing dashboard or grader formatting.
* Managing global mutable state.

## 3. Suggested structure

```text
src/
├── controllers/
│   ├── base_controller.py
│   ├── application_controller.py
│   ├── telemetry/
│   │   └── telemetry_controller.py
│   ├── fault/
│   │   └── fault_controller.py
│   └── diagnostic/
│       └── diagnostic_controller.py
```

`BaseController` defines the shared contract. Each concrete controller implements the behavior for its message domain. `ApplicationController` coordinates application-level lifecycle and integration; it must not duplicate the domain logic of the concrete controllers.

## 4. BaseController contract

Define a minimal abstract contract using Python's standard library, preferably `abc.ABC` and `abc.abstractmethod`.

The contract should establish how a controller receives a complete message or the corresponding routed input, processes it, and reports the result.

The exact parameter and return types must reuse the stabilized project interfaces rather than introduce a second message model.

Requirements:

* Use type hints.
* Define only methods that are genuinely common to all controllers.
* Keep dependencies explicit through constructor injection.
* Do not implement CAN reception, reassembly, or protocol-specific behavior in the base class.
* Do not force unrelated controllers to implement methods they do not need.
* Avoid a generic base class filled with conditional logic based on message type.

A controller should return a structured result or communicate through the established service interfaces. It must not depend on how the result will eventually be displayed.

## 5. Concrete controllers

### 5.1 TelemetryController

**Responsibility:** process decoded telemetry messages from the four power modules.

CAN identifiers handled by the telemetry routes:

* `0x100`
* `0x101`
* `0x102`
* `0x103`

Responsibilities:

1. Receive the routed input.
2. Invoke or consume the established telemetry decoder result, according to the stabilized routing contract.
3. Validate that the result is valid before updating state.
4. Update the corresponding module's telemetry state through `ApplicationState`.
5. Update the relevant statistics through `StatsService`.
6. Publish any application event required by the established event contract.
7. Return an explicit processing result.

The controller must not parse raw CAN payloads independently or duplicate decoder logic.

### 5.2 FaultController

**Responsibility:** process decoded fault messages.

CAN identifier:

* `0x1F0`

Responsibilities:

1. Receive the routed fault message.
2. Consume the fault decoder result.
3. Validate the result.
4. Update the application's fault state.
5. Update the relevant statistics.
6. Publish the corresponding fault event through the event publication service.
7. Return an explicit processing result.

Fault processing must remain independent of dashboard presentation and grader serialization.

### 5.3 DiagnosticController

**Responsibility:** process completed diagnostic messages.

Diagnostic CAN identifier range:

* `0x6F0–0x6F3`

The transport layer is responsible for reconstructing diagnostic messages. The controller must only receive a completed message or the established equivalent; it must not reassemble First Frames and Consecutive Frames.

Responsibilities:

1. Receive the completed diagnostic message through the established route.
2. Consume the diagnostic decoder result.
3. Validate the result and reject invalid or incomplete data.
4. Update diagnostic state through `ApplicationState`, if applicable.
5. Update diagnostic statistics.
6. Publish a `diag_complete` event when a valid diagnostic operation completes.
7. Return an explicit processing result.

**Timestamp requirement:** preserve the `ts_ns` timestamp captured at diagnostic reassembly completion. Do not replace it with the controller's processing time.

## 6. ApplicationController

`ApplicationController` coordinates the application lifecycle and connects the initialized components.

Responsibilities:

* Coordinate startup and shutdown.
* Hold or coordinate the application's injected dependencies.
* Connect routes and controllers to the required services.
* Select the appropriate output implementation for the execution mode.
* Ensure that application state and services are initialized before message processing begins.

It must not contain telemetry, fault, or diagnostic decoding logic.

## 7. Error handling

Controllers must handle expected processing failures explicitly.

* Invalid decoded results must not corrupt application state.
* Unsupported or malformed messages must not terminate the entire application.
* Unexpected programming errors must not be silently swallowed.
* Logging must go to `stderr` or the configured logging destination, never directly to grader `stdout`.
* Error handling must not introduce retries or CAN transmissions.
* A failure in one message must not prevent subsequent valid messages from being processed.

Use the project's established result and error conventions. Do not introduce a parallel exception hierarchy unless necessary.

## 8. Dependency rules

Allowed dependency direction:

```text
Routes
  |
  v
Controllers
  |
  v
Services
  |
  v
Application State / Event Publication / Statistics
```

Controllers may use protocol result models and established decoder interfaces. They must not import the concrete SocketCAN adapter, terminal dashboard, or grader serializer.

Dependencies must be injected explicitly. Do not create module-level singleton services or circular imports.

## 9. Tests

Add unit tests for each controller covering:

* A valid message is processed correctly.
* State is updated through the appropriate service.
* The correct event is published.
* Statistics are updated as expected.
* An invalid decoded result does not update valid application state.
* Service failures are handled according to the project error contract.
* Diagnostic completion preserves the original `ts_ns`.
* Processing one invalid message does not prevent subsequent valid messages.
* Controllers do not perform CAN transmission or direct terminal output.

Use mocks or lightweight test doubles for service dependencies. Tests must not require a physical CAN interface.

## 10. Definition of done

* [x] `BaseController` defines a minimal, documented contract.
* [x] Telemetry, fault, and diagnostic controllers are implemented.
* [x] Controllers use the stabilized message, decoder, and service interfaces.
* [x] `ApplicationController` coordinates lifecycle without duplicating domain logic.
* [x] No controller reads CAN frames or performs reassembly.
* [x] No controller prints directly to `stdout`.
* [x] Diagnostic timestamps are preserved.
* [x] Unit tests pass.
* [x] Both normal and grader modes remain compatible with the application. (verified offline by `integration/application/` through `main.build_application` in both modes; the live `vcan0` check on the Pi is pending)

