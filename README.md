# Conet Tactile — Industrial Tactile Inspection

Industrial quality inspection that no camera can do. A flexible, peel-and-stick pressure-sensing mesh that turns any conveyor into a per-part tactile inspection station, calibrated with five known-good samples.

This repository contains:

| Path | Description |
|------|-------------|
| `web/` | Public marketing site (static HTML / CSS, no framework, no Tailwind). |
| `backend/` | FastAPI inference & ingestion service (`/ingest`, `/calibrate`, `/inspect`, `/events`). |
| `firmware/` | Reference scanning firmware for the Tactile Mesh row/column multiplexer (Arduino / STM32 stub). |
| `docs/` | Architecture, installation guide, and operational runbook. |
| `PROJECT_BRIEF.md` | Full product, market, and technology brief. |
| `BOM.md` | Bill of materials with vendors and target unit cost. |

## Product lineup

- **Tactile Mesh** — flexible peel-and-stick pressure-sensing sheet, shipped as a roll, cut to belt width on-site.
- **Tactile Edge** — small inference appliance (Jetson Orin Nano class) that reads the mesh and runs anomaly scoring locally.
- **Tactile Cloud** — managed AI service that auto-calibrates from five known-good samples and continuously improves with fleet data.

## Quick start

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
