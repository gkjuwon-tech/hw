import { useState } from "react";
import { PageHeader } from "../components/PageHeader";
import { Step } from "../components/Step";

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
    title: "Five known-good parts",
    body: "Run five parts you have manually verified as defect-free down the belt. Each crossing is auto-detected by line vibration.",
  },
  {
    num: "03",
    title: "Optional: known-bad",
    body: "Run 5–20 known-bad parts for false-positive tuning. Skippable for a first deployment; recommended before going live.",
  },
  {
    num: "04",
    title: "Go live",
    body: "Confirm the one-class baseline summary, set the reject threshold, and arm the line. Scores stream to every dashboard.",
  },
];

export function CalibrationWizard(): JSX.Element {
  const [active, setActive] = useState(0);

  const stateOf = (i: number): StepState => {
    if (i < active) return "done";
    if (i === active) return "active";
    return "pending";
  };

  return (
    <div className="page">
      <PageHeader
        eyebrow="02 — Calibrate"
        title="The five-sample calibration."
        lede="Conet's one-class baseline learns from five parts you trust. Four phases, each with a single decision; total time end-to-end is typically 4–9 minutes."
      />

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
          marginTop: "2rem",
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
            fontSize: "0.85rem",
            letterSpacing: "0.06em",
          }}
        >
          Phase {active + 1} / {PHASES.length}
        </p>
        <button
          type="button"
          className="btn btn--lime"
          onClick={() => setActive((i) => Math.min(PHASES.length - 1, i + 1))}
          disabled={active === PHASES.length - 1}
        >
          Next phase
          <span className="arrow" aria-hidden="true">
            {" →"}
          </span>
        </button>
      </div>

      <div className="card" style={{ marginTop: "3rem" }}>
        <p className="eyebrow">
          <span className="eyebrow__dot" aria-hidden="true" />
          What gets shipped to the cloud
        </p>
        <h3 className="h3" style={{ marginTop: "0.5rem" }}>
          Per-cell μ and σ. Nothing else.
        </h3>
        <p className="body">
          The calibration step does not upload raw tactile frames. Only the per-cell
          mean and standard deviation across your five samples, plus a small set of
          global descriptors (sum, max, centroid, area, peak gradient), are written
          back to Tactile Cloud. Raw frames stay on the Edge appliance for 24 hours
          and are then purged.
        </p>
      </div>
    </div>
  );
}
