# Conet Tactile — Edge Agent

The on-device daemon that runs on every Tactile Edge appliance (Jetson Orin
Nano class). It is the **only** code path that talks to the physical scanner
hardware in production. It also serves the **on-device kiosk** to the
appliance's integrated touch display over loopback HTTP — there is no
separate desktop installer for operators to download. The FastAPI cloud and
the fleet-management web console are pure consumers of what this agent
emits.

```
                       ┌───────────────────────────────────────────┐
USB-CDC                │  Tactile Edge — Jetson Orin Nano 8 GB     │
(serial, 200 Hz)       │                                           │
┌────────────┐         │  ┌─────────────┐    ┌──────────────────┐  │
│  Scanner   │ ──CONT─▶│  │  scanner.py │ ──▶│      agent.py    │  │
│  TS-G4 MCU │  frame  │  │  CRC, sync  │    │  inference +     │  │
└────────────┘         │  └─────────────┘    │  cloud client    │  │
                       │  ┌─────────────┐    └──────────────────┘  │
                       │  │telemetry.py │ ──┐                      │
                       │  │ tegrastats  │   │                      │
                       │  └─────────────┘   │                      │
                       └────────────────────┼──────────────────────┘
                                            │ HTTPS
                                            ▼
                                ┌────────────────────────┐
                                │  Tactile Cloud         │
                                │  (this repo's backend) │
                                └────────────────────────┘
```

## Install

The reference image for the Edge is a stock NVIDIA L4T 35.x rootfs. The
agent installs into a Python venv at `/opt/conet/edge_agent/`:

```bash
sudo apt-get install -y python3-venv python3-pip
sudo python3 -m venv /opt/conet/edge_agent
sudo /opt/conet/edge_agent/bin/pip install -e .
sudo cp systemd/conet-edge-agent.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now conet-edge-agent
```

## Configure

Edit `/etc/conet/edge.env` (or set env vars directly):

```ini
CONET_EDGE_CLOUD_URL=https://api.conet.studio
CONET_EDGE_API_KEY=ctk_live_xxxxxxxxxxxxxxxxxxxxxx
CONET_EDGE_ID=edge-floor3-line7
CONET_EDGE_LINE_ID=line-7
CONET_EDGE_SCANNER_PORT=/dev/ttyACM0
CONET_EDGE_SCAN_RATE_HZ=200
CONET_EDGE_HEARTBEAT_PERIOD_S=2.0
```

The first time the agent runs, it enrolls itself with the cloud (idempotent)
and then starts streaming. If the scanner USB is unplugged or the cloud is
unreachable, the agent retries with capped exponential backoff and keeps a
local on-disk ring buffer at `/var/lib/conet/edge_agent/spool/`.

## Frame format on the wire

The MCU sends a packed C struct on the USB-CDC tty:

```c
struct frame_t {
  uint32_t magic;        // 0x434F4E54  ('CONT')
  uint16_t rows;
  uint16_t cols;
  uint32_t seq;          // monotonic counter
  uint32_t timestamp_us; // µs since MCU boot
  uint16_t crc;          // CRC-16/CCITT over data
  uint16_t _pad;
  uint8_t  data[rows*cols]; // row-major, 8 bits per cell
};
```

`scanner.FrameReader` is the host-side parser and is independently unit
tested in `tests/test_scanner.py`.

## What gets sent

| Endpoint | Cadence | Payload |
|---|---|---|
| `POST /v1/lines/{line_id}/inspect` | per detected part (line speed × belt vibration FFT) | `{data: [..]}`, returns score + verdict |
| `POST /v1/lines/{line_id}/frames` | during calibration only | raw frame for buffering |
| `POST /v1/edges/{edge_id}/heartbeat` | every `CONET_EDGE_HEARTBEAT_PERIOD_S` | cpu/gpu/temp/inference latency |

The agent never uploads continuous raw frames — only per-part inspect
payloads and calibration buffers. This is the same posture as Tactile
Cloud's documented privacy contract.
