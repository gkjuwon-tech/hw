# Conet Tactile — Industrial Tactile Inspection

Industrial quality inspection that no camera can do. A flexible, peel-and-stick pressure-sensing mesh that turns any conveyor into a per-part tactile inspection station, calibrated with five known-good samples.

This repository contains:

| Path | Description |
|------|-------------|
| `web/` | Public marketing site (static HTML / CSS, no framework, no Tailwind). |
| `backend/` | FastAPI inference & ingestion service (`/ingest`, `/calibrate`, `/inspect`, `/events`). |
| `firmware/` | Reference scanning firmware for the Tactile Mesh row/column multiplexer (Arduino / STM32 stub). |
| `hardware/pcb/` | Custom Scanner PCB sources (README, markdown schematic; Gerbers/BOM/CPL land in a follow-up). |
| `docs/` | Architecture, installation guide, and operational runbook. |
| `PROJECT_BRIEF.md` | Full product, market, and technology brief. |
| `BOM.md` | Bill of materials with vendors and target unit cost. |
| `HOW_IT_WORKS.md` | Korean-language product overview — what it is, where the HW/SW boundary lives. |
| `HARDWARE_BUILD_GUIDE.md` | Korean-language step-by-step build guide for first prototype unit (shopping links + assembly + firmware + first inspect). |

## Product lineup

- **Tactile Mesh** — flexible peel-and-stick pressure-sensing sheet, shipped as a roll, cut to belt width on-site.
- **Tactile Edge** — small inference appliance (Jetson Orin Nano class) that reads the mesh and runs anomaly scoring locally.
- **Tactile Cloud** — managed AI service that auto-calibrates from five known-good samples and continuously improves with fleet data.

## Quick start

### Desktop App (Windows)

> [!WARNING]
> Do NOT use GitHub's "Download ZIP" button to download the .exe files. GitHub ZIP downloads do not support Git LFS, so the executables will be broken 1KB pointer files.
> **To download the Windows App:** Go to [GitHub Actions (CI)](https://github.com/gkjuwon-tech/hw/actions/workflows/ci.yml) -> Click the latest successful run -> Scroll down to **Artifacts** -> Download Conet-Tactile-Windows-Setup.

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
