# Conet Tactile — Project Brief

> **Industrial tactile inspection for high-throughput production lines.**
> A thin, flexible, peel-and-stick pressure-sensing mesh that turns any conveyor into a per-part tactile inspection station, paired with a managed AI service that calibrates itself from five known-good samples.

---

## 1. Problem

Modern factory quality inspection is dominated by machine vision (Cognex, Keyence, Sick, Basler). Vision works well for visible-surface defects on rigid, opaque, well-lit objects. It is **structurally weak** for a large class of defects:

- Internal voids, missing fill, cracks invisible to the surface.
- Soft / deformable / non-rigid products (baked goods, meat patties, soft packaging, cosmetics, fabrics).
- Translucent, matte-black, highly reflective surfaces.
- Tactile properties: stiffness, hardness, spring-back, mass-per-unit-area, surface friction.

These categories are inspected today by:
- Sample-based lab testing (slow, statistical, downstream of the line).
- X-ray (capital-intensive, regulatory burden, slow).
- Manual touch inspection (expensive, inconsistent, doesn't scale).
- "Hope" (most SMB lines).

Camera vendors do not solve this because cameras cannot feel. Existing tactile sensors solve a different problem — they live on **robot gripper fingertips** ($500–$5,000 per point), not on production lines.

## 2. Product

### 2.1 Tactile Mesh (hardware, consumable-like)

A flexible pressure-sensing sheet that ships as a roll and is installed on top of (or under a low-friction cover over) an existing conveyor belt. Customer cuts to belt width with the included cutter, peels the adhesive backing, and lays it down. No re-tooling, no line stoppage longer than ~30 minutes.

- Form factor: roll, 200 / 350 / 500 / 750 mm × up to 5 m per roll.
- Sensing principle: piezo-resistive textile matrix (Velostat-class for prototype; Eeonyx EeonTex-class for production) with row/column conductive bus.
- Spatial resolution: 5 mm pitch (≈ 200 cells per cm²).
- Temporal resolution: 1 kHz frame rate per scanner board, decimated to 200 Hz uplink.
- Pressure range: 0.5 kPa – 200 kPa, 8-bit per cell (16-bit raw at the scanner).
- Operating temperature: 0–60 °C (food-grade variant in roadmap: −20–80 °C).
- Lifetime: 6–12 months under continuous use; sold as a consumable subscription.

### 2.2 Tactile Edge (hardware, durable)

A small fanless inference appliance that the Tactile Mesh plugs into. One Edge per line.

- Compute: NVIDIA Jetson Orin Nano 8 GB (or equivalent).
- I/O: 4× shielded ribbon inputs (one per mesh segment), 1× PoE in, 1× USB-C, 1× HDMI for on-site debug.
- Local inference latency: < 50 ms per part.
- Stores last 24 h of frames locally; uploads features (not raw frames) to Tactile Cloud.
- IP54, DIN-rail mount or magnetic base.

### 2.3 Tactile Cloud (managed AI service)

The actual moat. Customer onboarding workflow:

1. Customer plugs Edge in and scans a QR code.
2. Cloud auto-detects line speed via FFT on idle-belt vibration.
3. Customer runs **five known-good parts** down the belt and taps "Calibrate" in the web console.
4. Cloud trains a one-class anomaly model (PaDiM-like over tactile feature maps) from those five signatures.
5. Customer runs **5–20 known-bad parts** (optional) for false-positive tuning.
6. Live. Cloud streams anomaly scores back to Edge for sub-100 ms reject decisions, mirrors the dashboard for line managers.

Cloud also runs:
- Fleet-level transfer learning (a new customer on a similar product gets a warm-start model).
- Drift detection per cell (catches mesh wear before false positives ramp).
- Webhook + OPC-UA + PROFINET integrations for in-line reject actuators.

## 3. Market

### 3.1 Initial wedge (Korea + Japan, year 1)

We are deliberately NOT competing with Cognex / Keyence / Sick in their domains. We target categories where vision is structurally weak:

| Vertical | Pain | Annual lines (KR + JP) |
|----------|------|-----------|
| Bakery & confectionery | internal fill, springiness, sandwich layer count | ~2,400 |
| Pharmaceutical capsules & soft-gels | fill weight, capsule deformation, void | ~900 |
| Processed meat / patty / sausage | thickness, fat-distribution, springback | ~1,800 |
| Cosmetics filling (cushion, pump, tube) | pump chamber fill, cap torque proxy | ~1,500 |
| Garment & technical textile | seam thickness, ply count, double-feed | ~3,000 |
| Semiconductor back-end (die attach) | bondline pressure profile post-cure | ~600 |
| Additive manufacturing serial parts | internal voids, layer cohesion | ~400 |

Reasonable serviceable wedge: ~10,000 production lines, ~$5,000–$15,000 ARPU per line per year. **TAM (wedge only): ~$60–150 M ARR**, before global expansion.

### 3.2 Why now

- Flexible piezo-resistive textiles dropped below $40/m² in 2024 (Eeonyx, Velostat, sensing-knit suppliers).
- Jetson Orin Nano cleared the $250 ASP threshold for fanless industrial deployment.
- Anomaly-detection AI (PaDiM, PatchCore, EfficientAD) matured for one-class regimes — the algorithmic backbone is now off-the-shelf and runs on Orin Nano.
- Korean / Japanese SMB factories are under acute labor cost pressure post-2024 minimum wage hikes; the operational TCO of human touch-inspection is now visible on the P&L.

### 3.3 Why this is defensible vs incumbents

- **Cognex / Keyence cannot cannibalize themselves.** ~70% of their margin comes from on-site integration engineer billables; a peel-and-stick roll destroys that line item.
- **Chinese hardware copies will appear.** Defense is in the AI calibration pipeline, the fleet-level transfer learning, and the consumable subscription billing — not the sheet itself.
- **Patent surface:** (a) shipping form factor + installer-free workflow, (b) five-sample one-class calibration with FFT-derived line-speed auto-detection, (c) per-cell drift compensation tied to consumable replacement signaling.

## 4. Business model

| Line item | Pricing | Margin target |
|-----------|---------|---------------|
| Tactile Mesh (consumable) | $480 (200 mm × 1 m) … $4,800 (750 mm × 5 m) per roll | 30–40 % |
| Tactile Edge (durable) | $1,290 list, $0 with 24-mo SaaS contract | 15 % |
| Tactile Cloud — Line plan | $1,200 / line / month | 80–85 % |
| Tactile Cloud — Throughput plan | $0.018 / part inspected | 80–85 % |
| Enterprise custom model | $25,000 setup + $3,000 / month | 70 % |

Target blended gross margin year 3: **62 %.**

## 5. Technical architecture

```
   ┌──────────────────────────────────────────────────────────────┐
   │ Conveyor belt (existing)                                     │
   │  ┌────────────────────────────────────────────────────────┐  │
   │  │ Tactile Mesh sheet (Velostat / Eeonyx, 5 mm pitch)     │  │
   │  └────────────────────────────────────────────────────────┘  │
   │           │ row × col analog                                 │
   │           ▼                                                  │
   │  ┌────────────────────────────────────────────────────────┐  │
   │  │ Scanner board: STM32G4 + 74HC4067 mux + INA826 + ADS1115│ │
   │  └────────────────────────────────────────────────────────┘  │
   │           │ USB / RS-485 / Ethernet                          │
   │           ▼                                                  │
   │  ┌────────────────────────────────────────────────────────┐  │
   │  │ Tactile Edge (Jetson Orin Nano 8 GB)                    │ │
   │  │  - frame buffer (10 s ring)                             │ │
   │  │  - part segmentation (peak detection on belt-direction) │ │
   │  │  - on-device PaDiM-lite anomaly score                   │ │
   │  │  - GPIO/RS-485 reject actuator                          │ │
   │  └────────────────────────────────────────────────────────┘  │
   │           │ features only (no raw frames) over HTTPS         │
   └───────────┼──────────────────────────────────────────────────┘
               ▼
       ┌──────────────────────────────────────────────────────┐
       │ Tactile Cloud (FastAPI + Postgres + S3 + worker)     │
       │  /ingest      stream features                         │
       │  /calibrate   train one-class baseline (5+ samples)   │
       │  /inspect     score (also runs at Edge; this is cloud │
       │               fallback + audit trail)                 │
       │  /events      SSE stream to dashboard                 │
       │  /lines       fleet view, drift, consumable status    │
       └──────────────────────────────────────────────────────┘
```

This repository implements the cloud-side of the above as a minimal-but-real FastAPI service with a one-class baseline (Mahalanobis distance over per-cell mean/cov + per-part aggregate features). Production will replace the baseline with a PaDiM/PatchCore variant adapted for tactile feature maps — the API surface stays the same.

## 6. Roadmap

| Quarter | Milestone |
|---------|-----------|
| Q1 | Velostat-based prototype, 200 mm × 500 mm, 5 mm pitch, single Edge. First paid pilot with one Korean bakery OEM. |
| Q2 | Eeonyx-based pilot rolls. Self-serve calibration in web console. Three pilots live. |
| Q3 | PaDiM-lite on Edge, sub-50 ms inference. OPC-UA integration. Ten pilots. |
| Q4 | Consumable subscription billing. Fleet-level transfer learning. First repeat-purchase customers. |
| Y2 | Pharmaceutical-grade variant (cleanroom-compatible, IP69K). FDA 21 CFR Part 11 audit trail. |

## 7. Risks

| Risk | Mitigation |
|------|------------|
| Mesh durability under industrial wear | Sold as consumable subscription; drift detection signals replacement before false positives. |
| Customer integration drag (PLC / actuator wiring) | Ship Edge with standard relay output + library of pre-built PLC profiles. |
| Chinese hardware copies | Moat in cloud + calibration pipeline, not sheet itself. |
| Vision incumbent FUD | Public benchmark: same line, our system vs camera baseline, on bakery-style soft defects. |
| Food-contact regulatory | Mesh sits *under* belt or under a food-grade cover for direct-contact verticals. |

## 8. Team needs (year 1)

- 1× hardware engineer (mesh + scanner board)
- 1× firmware engineer (STM32, signal conditioning)
- 1× ML engineer (anomaly detection, drift)
- 1× full-stack (cloud + dashboard) — overlaps with ML engineer initially
- 1× pilot customer success engineer (Korean-speaking, industrial floor experience)

This repository is the starting point for the **cloud + landing site + reference firmware** tracks.
