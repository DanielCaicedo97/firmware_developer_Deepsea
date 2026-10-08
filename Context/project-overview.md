# DeepSea CAN Diagnostic Tool

## Project Overview

This project is a diagnostic tool designed to monitor the internal CAN bus of a DC Fast Charger and provide a clear view of the status of its power modules.

The charger consists of **four power modules**, each responsible for part of the overall charging system. The diagnostic tool runs on the main controller and continuously monitors the communication between the controller and these modules.

### System Overview

The system can be understood as four independent power-module stations:

```text
                    DC Fast Charger
                           │
                     Internal CAN Bus
                           │
          ┌────────────────┼────────────────┐
          │                │                │
      Module 0         Module 1         Module 2         Module 3
      0x100/0x6F0      0x101/0x6F1      0x102/0x6F2      0x103/0x6F3
          │                │                │                │
          └────────────────┴────────────────┴────────────────┘
                           │
                           ▼
                  CAN Diagnostic Tool
```

The tool receives CAN traffic from the bus and identifies the frames that belong to the diagnostic system.

### CAN Traffic

Several types of CAN messages are present on the bus:

* **Module telemetry** — electrical and operating information from each power module.
* **Fault messages** — indicate diagnostic faults associated with a module.
* **Identification messages** — contain the serial number and firmware version of each module.
* **Unrelated traffic** — other CAN frames that are present on the same bus but are not relevant to the diagnostic tool.

The diagnostic tool must therefore distinguish between relevant and unrelated traffic before processing the messages.

### Frame Filtering

The main relevant CAN identifiers are:

| CAN ID            | Purpose               |
| ----------------- | --------------------- |
| `0x100` – `0x103` | Module telemetry      |
| `0x1F0`           | Fault information     |
| `0x6F0` – `0x6F3` | Module identification |
| `0x200` – `0x2FF` | Unrelated bus traffic |

Only the frames required by the diagnostic system should be processed. Unrelated traffic must be ignored.

### Module Monitoring

For each of the four modules, the tool maintains its current diagnostic information, including:

* Electrical measurements.
* Operating status.
* Fault status.
* Identification information.
* Firmware version.

The four modules operate independently, so information belonging to one module must not interfere with the state of another module.

### Identification Messages

Module identification information is longer than a single CAN frame and is therefore transmitted across multiple frames.

The diagnostic tool must reconstruct these messages while the bus continues to carry traffic from the other modules.

This means that the tool must be able to maintain independent information for the four modules while processing a single continuous CAN stream.

### Robustness

The CAN bus may contain incomplete or invalid diagnostic sequences.

The tool must continue operating correctly when:

* A diagnostic sequence starts without a valid beginning.
* A new diagnostic message replaces an unfinished one.
* A message declares an invalid size.
* Frames arrive with an unexpected sequence.
* Diagnostic messages are repeatedly started but abandoned.

These situations must affect only the corresponding module and must not compromise the monitoring of the other modules.

### Output

The application provides two operating modes:

**Normal mode**

A terminal dashboard presents the current state of the four power modules, including their electrical readings, faults, and identification information.

**Grader mode**

The application exposes its results as a stream of newline-delimited JSON events. This allows the automated evaluation system to verify telemetry, faults, identification messages, and processing statistics.

### Main Objective

The overall objective is to build a reliable diagnostic layer between the CAN bus and the system operator:

```text
              CAN BUS
                 │
                 ▼
          Frame reception
                 │
                 ▼
             Filtering
                 │
        ┌────────┼────────┐
        ▼        ▼        ▼
    Telemetry  Fault   Identification
        │        │        │
        │        │    Reassembly
        │        │        │
        └────────┼────────┘
                 ▼
          Module state
                 │
                 ▼
          Diagnostic output
```

The design should prioritize **correctness, isolation between modules, robustness to malformed traffic, and bounded state management**.
