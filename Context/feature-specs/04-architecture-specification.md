# Architecture Specification — DeepSea CAN Diagnostic

## 1. Before starting

**Always read `AGENTS.md` before starting.**

Before modifying the project, inspect the current repository structure and review:

* `docs/PROJECT_OVERVIEW.md`
* `docs/CODE_STANDARDS.md`
* `docs/architecture-context.md`
* `01-Communication_and_transport.md`
* `02-Protocol_Decoders.md`
* `03-Message_Routing.md`
* `CHALLENGE.md`
* `ADAPTER.md`

This specification establishes the target architecture for the entire application. Review the existing implementation before moving, renaming, or creating files. Reuse working components where appropriate and avoid introducing duplicate abstractions.

## 2. Goal

Reorganize the project into a modular, maintainable architecture with clear boundaries between communication, transport, protocol decoding, routing, application logic, services, and output.

The architecture must support:

* Independent development and testing of each layer.
* Adding new message types without rewriting existing components.
* Replacing the communication transport without changing protocol or application logic.
* Reusing controllers and services where appropriate.
* Running the same application logic in normal and grader modes.
* Explicit dependency management and predictable error handling.

Apply SOLID principles where they improve maintainability and testability. Do not introduce unnecessary abstractions, interfaces, or layers solely to satisfy a design pattern.

## 3. Architectural principles

### 3.1. Single Responsibility Principle (SRP)

Each module and class must have one clearly defined responsibility.

Examples:

* Communication receives raw frames.
* Transport validates and reassembles messages.
* Protocol decoders interpret payloads.
* Routes dispatch messages to the appropriate controllers.
* Controllers coordinate application behavior.
* Services implement reusable operations.
* Output components render the dashboard or serialize grader events.

A class must not combine transport handling, protocol decoding, business logic, and output formatting.

### 3.2. Open/Closed Principle (OCP)

The application must allow new message categories and handlers to be added through registration and composition.

Adding a new message type should normally require new domain modules and route registration, rather than modifications to the central router or existing decoders.

### 3.3. Liskov Substitution Principle (LSP)

Concrete implementations of shared base classes must honor their documented contracts.

For example, a concrete controller must be usable wherever the application expects a `BaseController`, without changing the expected processing or error-handling behavior.

Do not introduce inheritance where composition provides a simpler solution.

### 3.4. Interface Segregation Principle (ISP)

Components must depend only on the operations they actually need.

Avoid large interfaces that combine communication, decoding, state management, event publication, and rendering.

Use small interfaces or protocols where multiple implementations or test doubles provide a concrete benefit.

### 3.5. Dependency Inversion Principle (DIP)

High-level application logic must not depend directly on low-level transport or output implementations.

For example:

* Controllers consume structured results rather than raw CAN frames.
* Routes depend on controller contracts rather than SocketCAN.
* Application composition supplies concrete implementations through dependency injection.
* Output services consume structured application events instead of owning protocol decoders.

## 4. Target project structure

Use the following structure as the target. Adapt names and retain existing modules where equivalent functionality already exists.

```
deepsea-can-diagnostic/
├── main.py
├── src/
│   ├── communication/
│   │   ├── __init__.py
│   │   ├── interface.py
│   │   ├── frame.py
│   │   └── socketcan.py
│   │
│   ├── transport/
│   │   ├── __init__.py
│   │   ├── transport.py
│   │   ├── reassembler.py
│   │   └── listener.py
│   │
│   ├── protocol/
│   │   ├── __init__.py
│   │   ├── common/
│   │   │   └── __init__.py
│   │   ├── telemetry/
│   │   │   ├── __init__.py
│   │   │   ├── decoder.py
│   │   │   └── models.py
│   │   ├── fault/
│   │   │   ├── __init__.py
│   │   │   ├── decoder.py
│   │   │   └── models.py
│   │   └── diagnostic/
│   │       ├── __init__.py
│   │       ├── decoder.py
│   │       └── models.py
│   │
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── common/
│   │   │   ├── __init__.py
│   │   │   ├── router.py
│   │   │   └── results.py
│   │   ├── telemetry/
│   │   │   ├── __init__.py
│   │   │   └── routes.py
│   │   ├── fault/
│   │   │   ├── __init__.py
│   │   │   └── routes.py
│   │   ├── diagnostic/
│   │   │   ├── __init__.py
│   │   │   └── routes.py
│   │   └── routes_init.py
│   │
│   ├── controllers/
│   │   ├── __init__.py
│   │   ├── base_controller.py
│   │   ├── application_controller.py
│   │   ├── telemetry/
│   │   │   ├── __init__.py
│   │   │   └── telemetry_controller.py
│   │   ├── fault/
│   │   │   ├── __init__.py
│   │   │   └── fault_controller.py
│   │   └── diagnostic/
│   │       ├── __init__.py
│   │       └── diagnostic_controller.py
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── event_publisher.py
│   │   ├── application_state.py
│   │   └── stats_service.py
│   │
│   ├── output/
│   │   ├── __init__.py
│   │   ├── dashboard.py
│   │   └── grader.py
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── message.py
│   │   └── application_event.py
│   │
│   └── config/
│       ├── __init__.py
│       ├── constants.py
│       └── settings.py
│
├── tests/
│   ├── communication/
│   ├── transport/
│   ├── protocol/
│   ├── routes/
│   ├── controllers/
│   └── services/
│
├── docs/
├── AGENTS.md
├── README.md
└── .gitignore
```

This is a logical target, not a requirement to create every file or directory immediately. Empty folders and unnecessary wrapper modules should not be added. If a shared model already exists in another appropriate module, reuse it rather than duplicating it.

## 5. Layer responsibilities

### 5.1. Communication

**Location:** `src/communication/`

Responsibilities:

* Define the generic communication interface.
* Receive raw CAN frames.
* Implement the SocketCAN adapter.
* Handle communication-specific failures and lifecycle.

This layer must not know about telemetry, fault semantics, diagnostic payload formats, application state, or output modes.

### 5.2. Transport

**Location:** `src/transport/`

Responsibilities:

* Consume frames from the communication interface.
* Validate frame-level properties.
* Reassemble multi-frame diagnostic messages.
* Maintain independent reassembly contexts.
* Deliver complete messages to the next layer.
* Preserve the diagnostic completion timestamp.
* Expose received-frame information required for statistics.

The transport layer must not decode application payloads or render output.

### 5.3. Protocol

**Location:** `src/protocol/`

Organize protocol implementations by message domain.

Each domain owns its decoder and its domain-specific decoded result models.

* `telemetry/`: decodes module telemetry.
* `fault/`: decodes fault events.
* `diagnostic/`: decodes completed diagnostic payloads.
* `common/`: contains only genuinely shared protocol utilities or definitions.

Protocol decoders must accept complete messages or payloads according to their defined contracts and return structured results.

They must not open sockets, perform transport reassembly, update application state, or publish grader output.

### 5.4. Routes

**Location:** `src/routes/`

Routes define the mapping between message identifiers and application handlers.

* `common/`: contains generic router behavior and routing result definitions.
* `telemetry/routes.py`: registers or exposes telemetry handlers.
* `fault/routes.py`: registers or exposes fault handlers.
* `diagnostic/routes.py`: registers or exposes diagnostic handlers.
* `routes_init.py`: composes the domain routes into the central router.

Routes must not contain protocol payload decoding or substantial business logic.

A route identifies the destination and delegates processing to the appropriate controller. Domain route modules may depend on controller contracts, but controllers must not depend on route configuration.

### 5.5. Controllers

**Location:** `src/controllers/`

Controllers coordinate application-level behavior. They consume structured routing or decoding results, apply application rules, update relevant state through services, and publish application events.

* `base_controller.py`: defines the reusable controller contract and shared behavior.
* `application_controller.py`: coordinates the application's overall processing flow when required.
* `telemetry/`: contains telemetry-specific application behavior.
* `fault/`: contains fault-specific application behavior.
* `diagnostic/`: contains diagnostic-specific application behavior.

Keep the base controller small. Domain controllers should inherit from it only when they genuinely share its contract.

Controllers must not receive raw CAN frames, implement frame reassembly, decode protocol bytes, render the dashboard, or serialize NDJSON.

### 5.6. Services

**Location:** `src/services/`

Services implement reusable operations that should not be embedded in route definitions or controller methods.

* `event_publisher.py`: defines the application event publication contract or shared publication behavior.
* `application_state.py`: maintains application state when a separate state service is justified.
* `stats_service.py`: manages the statistics required by the challenge.

Services must have explicit responsibilities and dependencies. Avoid creating a service for every function or wrapping simple data structures without a practical reason.

The source of `frames_processed` must remain connected to actual received CAN frames, excluding noise identifiers. Do not calculate it from completed messages.

### 5.7. Output

**Location:** `src/output/`

Output adapters consume structured events and expose them in the required presentation format.

* `dashboard.py`: implements normal-mode terminal output.
* `grader.py`: emits grader-compatible NDJSON to standard output and sends diagnostics to standard error.

Output formatting must not leak into controllers, routes, or protocol decoders.

Both output modes must consume the same application-level event contract.

### 5.8. Models

**Location:** `src/models/`

Contains shared cross-layer models, including:

* Complete-message abstractions that are genuinely shared.
* Application event envelopes and other cross-domain types.

Protocol-specific decoded result models belong in their respective protocol packages unless the existing codebase has a strong reason to centralize them.

Avoid multiple representations of the same information without a clear conversion boundary.

### 5.9. Configuration

**Location:** `src/config/`

* `constants.py`: protocol identifiers and fixed protocol constants.
* `settings.py`: runtime configuration such as interface selection and application mode.

Do not scatter CAN identifiers, limits, or other protocol constants across multiple modules.

## 6. Dependency direction

Use the following dependency flow as the architectural guide:

```
main.py
   |
   v
Application Composition
   |
   +---- Communication
   |         |
   |         v
   |      Transport
   |         |
   |         v
   |       Routes
   |         |
   |         v
   |     Controllers
   |         |
   |         v
   |       Services
   |         |
   |         v
   |       Output
```

Protocol decoders provide structured results to the routing or controller integration layer according to the existing contracts.

The diagram describes the runtime flow; it does not authorize circular imports. Dependencies must be defined through small contracts and explicit injection where needed.

Rules:

* `communication` must not import controllers, routes, or output.
* `transport` must not import dashboard or grader implementations.
* `protocol` must not depend on application controllers or output.
* `routes` may reference controller interfaces and protocol result contracts.
* `controllers` must not import concrete route configuration.
* `services` must not depend on dashboard rendering.
* `output` must not decode protocols or modify transport state.
* `main.py` is the composition root responsible for constructing and connecting concrete implementations.

Avoid circular imports. Shared contracts should live in the narrowest appropriate module.

## 7. Application lifecycle

The application entry point must compose the layers in a clear sequence:

1. Load and validate runtime configuration.
2. Construct the communication adapter.
3. Construct the transport layer and its dependencies.
4. Construct the protocol decoders and controllers.
5. Construct services and the selected output adapter.
6. Initialize and register domain routes.
7. Connect complete-message delivery to the routing/application flow.
8. Start processing.
9. Emit final statistics and close resources cleanly on shutdown.

Keep `main.py` focused on composition and lifecycle. It must not contain protocol decoding, route matching algorithms, controller business rules, or dashboard rendering logic.

## 8. Event and state management

Use structured application events to communicate between the controller layer and output adapters.

Required event types include:

* `telemetry`
* `fault`
* `diag_complete`
* `stats`

Event payloads must preserve the values and metadata required by the challenge.

For diagnostic completion, the timestamp `ts_ns` must be captured when reassembly completes and preserved through every subsequent layer.

State ownership must be explicit. Keep only the latest values or bounded history needed by the application. Avoid retaining every received frame or completed message indefinitely.

Statistics must be based on the correct source of truth. In particular, `frames_processed` counts only challenge traffic frames and excludes noise.

## 9. Testing strategy

Tests must follow the architecture and verify layer contracts independently.

* Communication tests: adapter behavior and error handling.
* Transport tests: frame validation, reassembly, interleaving, abandonment, and bounded memory.
* Protocol tests: payload decoding and malformed input.
* Route tests: registration, dispatch, and unknown identifiers.
* Controller tests: application decisions, state updates, and event publication.
* Service tests: state, statistics, and event-publishing behavior.
* Output tests: dashboard behavior and exact grader NDJSON contract.
* Integration tests: complete messages flowing through the composed application.

Use `unittest` and the Python standard library. Inject test doubles instead of requiring physical CAN hardware or live generator traffic for unit tests.

Do not introduce tests that require prohibited libraries or cause CAN transmission.

## 10. Refactoring strategy

Apply the architecture incrementally.

1. Inspect the current tree and identify existing responsibilities.
2. Map each existing module to its target architectural layer.
3. Identify duplicated logic, circular dependencies, and mixed responsibilities.
4. Define or preserve the minimal shared contracts.
5. Move or rename modules only when necessary.
6. Update imports and tests alongside each change.
7. Run the existing tests after each logical refactoring step.
8. Verify both normal and grader execution paths.
9. Confirm all challenge restrictions remain satisfied.

Do not rewrite functioning protocol or transport logic solely to match a preferred filename.

Do not implement every planned layer in one change. Establish the boundaries first, then refactor incrementally.

## 11. Check when done

* [ ] `AGENTS.md` and the existing project documentation were reviewed.
* [ ] The current repository structure was inspected.
* [ ] Communication and transport responsibilities are separate.
* [ ] Protocol packages are organized by message domain.
* [ ] Routes are separated from controllers.
* [ ] Controllers are separated from services and output.
* [ ] Shared models and protocol-specific models have clear ownership.
* [ ] Dependencies follow a consistent direction without circular imports.
* [ ] Runtime construction and lifecycle remain in `main.py`.
* [ ] State and statistics have explicit ownership.
* [ ] Normal and grader modes share the same application logic.
* [ ] Existing challenge behavior and constraints are preserved.
* [ ] Tests pass after each refactoring step.
* [ ] No unnecessary abstractions, duplicate modules, or external dependencies were introduced.

## 12. Definition of done

The architecture refactoring is complete when each layer has a clear responsibility, dependencies flow in a predictable direction, domain modules can evolve independently, and the application can run in both required modes without duplicating protocol or application logic.

The final structure must support maintainability and future extension while remaining appropriately simple for the DeepSea challenge.
