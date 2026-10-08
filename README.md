<div align="center">
  <h1>DeepSea CAN Diagnostic Tool</h1>
  <p>
    <strong>Receive-only CAN bus monitor for DC Fast Charger power modules</strong>
  </p>

  <p>
    <img src="https://img.shields.io/badge/Python-3_stdlib_only-3776AB?logo=python&logoColor=white" alt="Python 3 standard library only">
    <img src="https://img.shields.io/badge/Platform-Raspberry_Pi_5-C51A4A?logo=raspberrypi&logoColor=white" alt="Platform: Raspberry Pi 5">
    <img src="https://img.shields.io/badge/Bus-SocketCAN-0A7BBB?logo=linux&logoColor=white" alt="Bus: SocketCAN">
    <img src="https://img.shields.io/badge/Status-In_Development-orange?logo=git" alt="Status: In development">
    <br>
    <img src="https://img.shields.io/badge/Made_in-Colombia_🇨🇴-FCD116?labelColor=003893" alt="Made in Colombia">
  </p>
</div>

---

## 📢 System Overview

**DeepSea CAN Diagnostic Tool** runs on the main controller of a DC Fast Charger and listens to its internal CAN bus. The charger's enclosure is sealed and live, so field engineers can't inspect the power modules directly. This tool gives them a live view instead.


* 🔋 **Decodes live telemetry**: voltage, current, temperature and status flags (enabled / fault / derated).
* ⚠️ **Reports fault codes**: overtemp, overvoltage, undervoltage and isolation fault.
* 🏷️ **Reassembles identification strings**: serial number and firmware version, sent across several CAN frames using ISO 15765-2-style segmentation.
* 🔇 **Ignores unrelated traffic**: noise on `0x200`–`0x2FF`.
* 🛡️ **Survives a messy bus**: orphan frames, restarted messages, oversized length claims, out-of-order sequence numbers and repeated abandonment. Memory stays bounded throughout.

> **Constraints:** Python 3 standard library only (`socket` + `struct`). No `python-can`, no `CAN_ISOTP`, no decoding libraries. The tool **never transmits** a CAN frame.

---

## 🚀 Quick Start

### Requirements

* Linux with SocketCAN (developed on a Raspberry Pi 5, aarch64, Raspberry Pi OS)
* Python 3 (no third-party packages)
* A CAN interface, for example the virtual `vcan0`

### Run

```bash
# Normal mode: in-place terminal dashboard
python3 main.py --iface vcan0

# Grader mode: NDJSON event stream on stdout, logs on stderr
python3 main.py --iface vcan0 --grader
```

### Generate test traffic

In a second terminal, start the challenge's traffic generator. It is used as-is and never modified:

```bash
python3 ~/challenge/can_generator/generator.py --iface vcan0 --duration 90
```

Use a longer duration (for example `600`) to check that memory stays flat over many abandonment cycles.

---

## 🖥️ Output Modes

### Normal Mode: Dashboard

An in-place terminal dashboard, drawn with plain ANSI codes (no `ncurses`, no UI library):

```text
DeepSea CAN Diagnostic Tool
---------------------------
Module 0:  412.3V  118.55A   47C   enabled=True  fault=False
Module 1:  405.1V  120.02A   45C   enabled=True  fault=False
Module 2:  399.8V  115.30A   46C   enabled=True  fault=True
Module 3:  410.0V  119.87A   44C   enabled=True  fault=False
---------------------------
Identification strings:
  0x6f0: SN:PMU-4471-A FW:2.3.1
  0x6f1: SN:PMU-4472-B FW:2.3.1
  0x6f2: SN:PMU-4473-C FW:2.4.0
  0x6f3: (not yet received)
---------------------------
Recent faults:
  module 2, code 1
```

### Grader Mode: NDJSON

One JSON object per line on **stdout**, flushed after every line. All diagnostics go to **stderr**.

```json
{"type": "telemetry", "module": 0, "seq": 4821, "voltage": 412.3, "current": 118.55, "temp_c": 47, "enabled": true, "fault": false, "derated": false}
{"type": "fault", "module": 2, "code": 1}
{"type": "diag_complete", "can_id": "0x6f0", "string": "SN:PMU-4471-A FW:2.3.1", "ts_ns": 88123456789}
{"type": "stats", "frames_processed": 15234}
```

---

## 📡 The Bus

| CAN ID | Purpose | Payload |
| :---: | :--- | :--- |
| `0x100`–`0x103` | Module telemetry (module 0–3) | voltage, current, temperature, status, seq |
| `0x1F0` | Fault code | module ID + fault code |
| `0x6F0`–`0x6F3` | Identification string (module 0–3) |First / Consecutive Frames, at most 64 bytes |
| `0x200`–`0x2FF` | Unrelated noise | ignored |

---

## 🏗️ System Architecture

The tool is layered so that the application cares about **messages and their meaning, not about how they physically arrived**. SocketCAN is the first communication implementation. The same layers above the transport boundary are designed to work unchanged over UART, SPI or a physical `can0`.

### Block Diagram

```text
┌────────────────────────────────────────────────┐
│         COMMUNICATION INTERFACE                │
│   SocketCAN (vcan0 / can0)  ·  UART  ·  SPI    │
└───────────────────────┬────────────────────────┘
                        │ raw frames / byte chunks
                        ▼
┌────────────────────────────────────────────────┐
│              RECEIVE BUFFER                    │
│   Bounded FIFO · protocol-agnostic             │
│   explicit overflow policy + counter           │
└───────────────────────┬────────────────────────┘
                        │
                        ▼
┌────────────────────────────────────────────────┐
│                 TRANSPORT                      │
│   CanTransport: single-frame + segmented       │
│   one reassembly context per source            │
└───────────────────────┬────────────────────────┘
                        │ Message(source, payload, timestamp)
                        ▼
┌────────────────────────────────────────────────┐
│                   ROUTER                       │
└──────────┬─────────────┬─────────────┬─────────┘
           ▼             ▼             ▼
     ┌──────────┐  ┌──────────┐  ┌──────────────┐
     │Telemetry │  │  Fault   │  │Identification│
     │ decoder  │  │ decoder  │  │   decoder    │
     └────┬─────┘  └────┬─────┘  └──────┬───────┘
          └─────────────┼───────────────┘
                        ▼
┌────────────────────────────────────────────────┐
│                 CONTROLLER                     │
│   Application state for the 4 modules          │
└───────────────────────┬────────────────────────┘
                        │
              ┌─────────┴─────────┐
              ▼                   ▼
     ┌─────────────────┐ ┌─────────────────┐
     │  Dashboard      │ │  Grader NDJSON  │
     │  (normal mode)  │ │  (stdout)       │
     └─────────────────┘ └─────────────────┘
```

Frames are processed **sequentially in a single loop**, while each module keeps its own independent state. This gives logical concurrency (interleaved messages from all 4 modules) with deterministic behavior and no threading.

---

## 🔍 Design Decisions

### Filtering Mechanism

Filtering happens in two stages:

1. **Kernel-level filter.** `setsockopt(SOL_CAN_RAW, CAN_RAW_FILTER, ...)` installs three id/mask pairs: `0x100/0x7FC`, `0x1F0/0x7FF` and `0x6F0/0x7FC`. Noise is discarded by the kernel before it reaches the process, so it costs no CPU and can't crowd real frames out of the receive queue when its rate rises mid-run.
2. **Router validation.** Every frame is still classified by exact ID in user space, so correctness never depends on the kernel filter alone.

`frames_processed` counts every frame received on a real ID, **including diagnostic frames that are later rejected**. Noise is never counted.

### Reassembly State Management

| Concern | Design |
| :--- | :--- |
| **Keying** | One reassembly context per identification CAN ID (`0x6F0`–`0x6F3`). There is no shared buffer, so interleaved messages can't corrupt each other. |
| **Bounding** | Exactly 4 contexts, created once at startup. Each holds at most 64 payload bytes. First Frames claiming more are rejected before anything is stored. |
| **Reset** | A context returns to idle on completion, invalid sequence, or rejection. A new First Frame replaces any message in progress. |
| **Expiry** | An optional inactivity timeout resets a context that stops making progress. It isn't needed for the memory bound, which holds by construction. |

How each bus situation is handled:

| Situation | Behavior |
| :--- | :--- |
| Orphan Consecutive Frame | Ignored, because no message is in progress |
| Restarting First Frame | Old attempt dropped, new one started |
| Oversized length (> 64 bytes) | First Frame rejected |
| Out-of-order sequence number | Attempt abandoned |
| Repeated abandonment | Next First Frame reuses the same fixed context, so memory doesn't grow |

None of these emits a `diag_complete` line, and none affects any other module.

---

## 📂 Repository Structure

```text
📦 Root
 ┣ 📜 main.py            # Entry point: CLI parsing and component composition
 ┣ 📂 src
 ┃ ┣ 📂 communication    # Communication interface, SocketCAN, receive buffer
 ┃ ┣ 📂 transport        # Transport interface, CAN framing and reassembly
 ┃ ┣ 📂 protocol         # Router + telemetry, fault and identification decoders
 ┃ ┣ 📂 controller       # Application state for the 4 modules
 ┃ ┣ 📂 services         # Dashboard and grader NDJSON output
 ┃ ┣ 📂 models           # Dataclasses: frames, messages, decoded data
 ┃ ┗ 📂 config           # Constants and runtime settings
 ┣ 📂 tests              # Offline tests with synthetic frames
 ┣ 📂 Context            # Project specs: overview, architecture, standards, workflow
 ┗ 📜 README.md
```

---


## 🗺️ Roadmap

- [x] **Specification:** project overview, architecture, code standards and workflow defined.
- [ ] **Communication:** SocketCAN receive-only interface with kernel filter.
- [ ] **Receive buffer:** bounded FIFO with overflow counter.
- [ ] **Transport:** CAN single-frame passthrough and segmented reassembly.
- [ ] **Protocol:** telemetry, fault and identification decoders.
- [ ] **Output:** grader NDJSON stream and terminal dashboard.
- [ ] **Verification:** offline tests and a live run on `vcan0`.

---

<div align="center">
  <p>Made with ❤️, ☕, and Python in Colombia</p>
</div>
