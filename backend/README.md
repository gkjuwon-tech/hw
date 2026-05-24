# Conet Tactile Cloud — backend

FastAPI service that powers the Tactile Cloud:

- **POST `/v1/lines`** — register a new conveyor line (mesh dimensions, customer tag).
- **POST `/v1/lines/{line_id}/frames`** — stream tactile frames from the Tactile Edge.
- **POST `/v1/lines/{line_id}/calibrate`** — finalize a one-class baseline from `n` known-good samples.
- **POST `/v1/lines/{line_id}/inspect`** — score a tactile frame against the calibrated baseline.
- **GET `/v1/lines/{line_id}/events`** — Server-Sent Events stream of recent inspections (for the dashboard).
- **GET `/v1/lines`** — list lines with status and drift indicators.

## Anomaly model (v0)

A deliberately small, fully analytical one-class baseline:

- During calibration, we keep `N` good samples (`N >= 5`), each a `H × W` pressure map.
- We compute per-cell mean `μ` and standard deviation `σ`.
- We compute global feature distribution (sum, max, centroid, area, peak gradient) over the same set.
- For inspection, we compute a Mahalanobis-style per-cell deviation `((x - μ) / σ)²` and aggregate
  to a single anomaly score, plus a hit-mask of cells exceeding `k·σ`.

This is the reference contract for the API surface. The production model swaps the analytical
baseline for a PaDiM/PatchCore-class detector adapted to tactile feature maps — the API stays
identical.

## Run locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000
# http://localhost:8000/docs
```

## Tests

```bash
pytest -q
ruff check .
```

## Project layout

```
app/
  main.py          FastAPI factory + lifecycle
  db.py            async SQLite engine
  core/
    config.py      settings
    storage.py     baselines on disk (numpy npz)
    anomaly.py     one-class baseline + scoring
  routers/
    lines.py       CRUD over lines
    frames.py      ingestion
    calibrate.py   build a baseline from buffered frames
    inspect.py     score a single frame
    events.py      SSE stream
tests/
  test_api.py      end-to-end happy path
```
