# Conet Tactile — Industrial Tactile Inspection

Industrial quality inspection that no camera can do. A flexible, peel-and-stick pressure-sensing mesh that turns any conveyor into a per-part tactile inspection station, calibrated with five known-good samples.

This repository contains:

| Path | Description |
|------|-------------|
| `web/` | Public marketing site (static HTML / CSS, no framework, no Tailwind). |
| `backend/` | FastAPI inference & ingestion service (`/ingest`, `/calibrate`, `/inspect`, `/events`). |
| `edge_api/` | Cloudflare Workers edge runtime — read-through cache + low-latency proxy in front of `backend/` for catalog, pricing, and kiosk config. |
| `edge_agent/` | On-device daemon that reads the scanner over USB-CDC and serves the on-box kiosk UI on the integrated touch display. |
| `firmware/` | Reference scanning firmware for the Tactile Mesh row/column multiplexer (Arduino / STM32 stub). |
| `hardware/pcb/` | Custom Scanner PCB sources (README, markdown schematic; Gerbers/BOM/CPL land in a follow-up). |
| `docs/` | Architecture, installation guide, and operational runbook. |
| `PROJECT_BRIEF.md` | Full product, market, and technology brief. |
| `BOM.md` | Bill of materials with vendors and target unit cost. |
| `HOW_IT_WORKS.md` | Korean-language product overview — what it is, where the HW/SW boundary lives. |
| `HARDWARE_BUILD_GUIDE.md` | Korean-language step-by-step build guide for first prototype unit (shopping links + assembly + firmware + display + first inspect). |

## Product lineup

- **Tactile Mesh** — flexible peel-and-stick pressure-sensing sheet, shipped as a roll, cut to belt width on-site.
- **Tactile Edge** — inference appliance + integrated touch display. Software (calibration UI, drift dashboard, OPC-UA bridge) is bundled and pre-installed; the operator interacts with the box directly on the line, no PC required.
- **Edge Care** — recurring maintenance plan that keeps the on-device software updated, syncs fleet baselines from Tactile Cloud, and ships replacement mesh rolls on schedule.

## Quick start

> The product is shipped as a single appliance — the touchscreen on the Tactile Edge box **is** the UI. There is no Windows / macOS / Linux installer to download. The on-box kiosk is served by the local `edge_agent` over loopback; the Chromium kiosk launcher is in [`edge_agent/systemd/`](edge_agent/systemd/).

### Landing page

```bash
cd web
python3 -m http.server 5173
# open http://localhost:5173
```

### Backend

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
uvicorn app.main:app --reload --port 8000
# docs: http://localhost:8000/docs
```

### Tests

```bash
cd backend
pip install -e ".[dev]"
pytest -q
ruff check .
```

## License

Proprietary. All rights reserved.
