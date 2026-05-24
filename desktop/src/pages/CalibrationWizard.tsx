/**
 * Calibration wizard.
 *
 * Four-phase guided flow for the five-sample calibration. This is a
 * thin client over the existing /v1/lines/{id}/calibrate endpoint —
 * the actual statistics are computed in the backend.
 */

import { useState } from "react";
import { PageHeader } from "../components/PageHeader";
import { Step } from "../components/Step";
import type { Line } from "../lib/types";

type StepState = "active" | "done" | "pending";

const PHASES: ReadonlyArray<{
  num: string;
  title: string;
  body: string;
}> = [
  {
    num: "01",
    title: "Pick a line",
    body: "Select the conveyor segment to calibrate. The mesh must be installed and the Edge appliance powered.",
  },
  {
    num: "02",
    title: "Five known-good",
    body: "Run five parts you have manually verified as defect-free down the belt. Each crossing is auto-detected.",
  },
  {
    num: "03",
    title: "Optional known-bad",
    body: "Run 5-20 known-bad parts for false-positive tuning. Skippable for a first deployment.",
  },
  {
    num: "04",
    title: "Arm the line",
    body: "Confirm the per-cell baseline, set the reject threshold, and arm. Scores stream to every dashboard.",
  },
];

export interface CalibrationWizardProps {
  lines: Line[];
}

export function CalibrationWizard({ lines }: CalibrationWizardProps): JSX.Element {
  const [active, setActive] = useState(0);
  const [pickedLine, setPickedLine] = useState<string | null>(null);

  const stateOf = (i: number): StepState => {
    if (i < active) return "done";
    if (i === active) return "active";
    return "pending";
  };

  return (
    <div className="page">
      <PageHeader
        eyebrow="CALIBRATE"
        title="Five-sample calibration"
        lede="One-class baseline from five parts you trust. Total wall-clock time end-to-end is typically 4-9 minutes."
      />

      <section className="card">
        <header className="card__head">
          <h3 className="h3">Pick a line</h3>
          <span className="mono" style={{ fontSize: 11, color: "var(--muted)" }}>
            phase 01
          </span>
        </header>
        <div className="card__body">
          {lines.length === 0 ? (
            <p className="lede">
              No lines registered yet. Register a line via{" "}
              <code className="mono">POST /v1/lines</code> first.
            </p>
          ) : (
            <select
              className="mono"
              style={{
                fontSize: 12,
                padding: "4px 6px",
                background: "var(--field)",
                border: "1px solid var(--line-strong)",
                boxShadow: "inset 1px 1px 0 var(--bevel-shadow)",
                width: "100%",
                maxWidth: 480,
              }}
              value={pickedLine ?? ""}
              onChange={(e) => setPickedLine(e.target.value || null)}
            >
              <option value="">— choose line —</option>
              {lines.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.id} · {l.customer_tag} ({l.rows}×{l.cols})
                </option>
              ))}
            </select>
          )}
        </div>
      </section>

      <ol className="steps">
        {PHASES.map((p, i) => (
          <Step
            key={p.num}
            num={p.num}
            title={p.title}
            body={p.body}
            state={stateOf(i)}
          />
        ))}
      </ol>

      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <button
          type="button"
          className="btn"
          onClick={() => setActive((i) => Math.max(0, i - 1))}
          disabled={active === 0}
        >
          ← Previous
        </button>
        <p
          className="mono"
          style={{
            color: "var(--muted)",
            fontSize: 11,
            letterSpacing: "0.06em",
          }}
        >
          Phase {active + 1} / {PHASES.length}
          {pickedLine ? ` · ${pickedLine}` : ""}
        </p>
        <button
          type="button"
          className="btn btn--primary"
          onClick={() => setActive((i) => Math.min(PHASES.length - 1, i + 1))}
          disabled={active === PHASES.length - 1 || !pickedLine}
        >
          Next phase →
        </button>
      </div>

      <div className="card">
        <header className="card__head">
          <h3 className="h3">What ships to the cloud</h3>
        </header>
        <div className="card__body">
          <p className="body">
            The calibration step does <b>not</b> upload raw tactile frames.
            Only the per-cell mean and standard deviation across your five
            samples, plus a small set of global descriptors (sum, max,
            centroid, area, peak gradient), are written back to Tactile
            Cloud. Raw frames stay on the Edge appliance for 24 hours and
            are then purged.
          </p>
        </div>
      </div>
    </div>
  );
}
