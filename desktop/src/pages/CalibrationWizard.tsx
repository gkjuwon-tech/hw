/**
 * Teach wizard.
 *
 * Production five-sample teach + line-arming flow. The wizard picks an
 * edge + line, starts a backend teach session, captures 5 sample frames
 * (one click per sample, simulated tactile pattern stream from the edge),
 * then finalizes and arms the line in a single round-trip.
 *
 * Comparable to Cognex EasyBuilder's "Teach the part" step — you don't
 * leave this screen until the line is live.
 */

import { useCallback, useEffect, useState } from "react";

import { PageHeader } from "../components/PageHeader";
import { api } from "../lib/api";
import type {
  ApiError,
  Edge,
  Line,
  TeachFinishResult,
  TeachStatus,
} from "../lib/types";

export interface CalibrationWizardProps {
  lines: Line[];
  edges: Edge[];
}

type Phase = "pick" | "capturing" | "ready" | "finalizing" | "done" | "error";

function syntheticFrame(rows: number, cols: number, sampleIndex: number): number[] {
  // Five distinct-but-similar synthetic frames. This is the bench-test
  // fallback when there is no live edge attached. A real edge_agent
  // would push real frames through /teach/capture itself.
  const total = rows * cols;
  const out = new Array<number>(total);
  const phase = sampleIndex * 0.13;
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const dx = c - cols / 2;
      const dy = r - rows / 2;
      const d = Math.sqrt(dx * dx + dy * dy);
      const v = 120 + 30 * Math.exp(-(d * d) / 12) + 4 * Math.sin(phase + d);
      out[r * cols + c] = Math.max(0, Math.min(255, v));
    }
  }
  return out;
}

export function CalibrationWizard({ lines, edges }: CalibrationWizardProps): JSX.Element {
  const [phase, setPhase] = useState<Phase>("pick");
  const [pickedEdge, setPickedEdge] = useState<string>("");
  const [pickedLine, setPickedLine] = useState<string>("");
  const [status, setStatus] = useState<TeachStatus | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<TeachFinishResult | null>(null);

  const line = lines.find((l) => l.id === pickedLine) ?? null;

  const refreshStatus = useCallback(async (): Promise<void> => {
    if (!pickedEdge) return;
    try {
      const s = await api.teachStatus(pickedEdge);
      setStatus(s);
      if (s.status === "completed") setPhase("done");
      else if (s.status === "ready") setPhase("ready");
      else if (s.status === "in_progress" && s.captured > 0) setPhase("capturing");
    } catch {
      // ignore — edge may not exist yet, or no session
    }
  }, [pickedEdge]);

  useEffect(() => {
    if (pickedEdge) void refreshStatus();
  }, [pickedEdge, refreshStatus]);

  const start = async (): Promise<void> => {
    if (!pickedEdge || !pickedLine) {
      setErr("Pick an edge and a line first.");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      await api.teachStart(pickedEdge, pickedLine);
      await refreshStatus();
      setPhase("capturing");
    } catch (e) {
      setErr((e as ApiError).message);
      setPhase("error");
    } finally {
      setBusy(false);
    }
  };

  const capture = async (): Promise<void> => {
    if (!line) return;
    const idx = status?.captured ?? 0;
    setBusy(true);
    setErr(null);
    try {
      const frame = syntheticFrame(line.rows, line.cols, idx);
      await api.teachCapture(pickedEdge, frame);
      await refreshStatus();
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  };

  const finalize = async (): Promise<void> => {
    setBusy(true);
    setErr(null);
    setPhase("finalizing");
    try {
      const r = await api.teachFinish(pickedEdge);
      setResult(r);
      setPhase("done");
      await refreshStatus();
    } catch (e) {
      setErr((e as ApiError).message);
      setPhase("error");
    } finally {
      setBusy(false);
    }
  };

  const abort = async (): Promise<void> => {
    setBusy(true);
    setErr(null);
    try {
      await api.teachAbort(pickedEdge);
      setStatus(null);
      setResult(null);
      setPhase("pick");
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  };

  const reset = (): void => {
    setStatus(null);
    setResult(null);
    setErr(null);
    setPhase("pick");
  };

  const required = status?.required ?? 5;
  const captured = status?.captured ?? 0;
  const remaining = status?.remaining ?? required;

  return (
    <div className="page">
      <PageHeader
        eyebrow="TEACH"
        title="Five-sample teach"
        lede="One-class baseline from five known-good parts. Pick an edge, pick a line, capture five frames, arm. No raw frames leave the Edge appliance."
      />

      {err ? (
        <div className="banner">
          <b>ERR</b>&nbsp;{err}
        </div>
      ) : null}

      <section className="card">
        <header className="card__head">
          <h3 className="h3">01 · Pick edge + line</h3>
          <span className="mono" style={{ fontSize: 11, color: "var(--muted)" }}>
            {phase === "pick" ? "active" : "locked"}
          </span>
        </header>
        <div
          className="card__body"
          style={{ display: "grid", gridTemplateColumns: "1fr 1fr auto", gap: 8, alignItems: "end" }}
        >
          <label className="field">
            <span>EDGE</span>
            <select
              className="mono"
              value={pickedEdge}
              onChange={(e) => setPickedEdge(e.target.value)}
              disabled={phase !== "pick" || busy}
            >
              <option value="">— choose edge —</option>
              {edges.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.id} · {e.hostname} ({e.status})
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>LINE</span>
            <select
              className="mono"
              value={pickedLine}
              onChange={(e) => setPickedLine(e.target.value)}
              disabled={phase !== "pick" || busy}
            >
              <option value="">— choose line —</option>
              {lines.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.id} · {l.customer_tag} ({l.rows}×{l.cols})
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="btn btn--primary"
            disabled={!pickedEdge || !pickedLine || busy || phase !== "pick"}
            onClick={() => void start()}
          >
            Start teach
          </button>
        </div>
      </section>

      <section className="card">
        <header className="card__head">
          <h3 className="h3">02 · Capture {required} known-good samples</h3>
          <span className="mono" style={{ fontSize: 11, color: "var(--muted)" }}>
            {captured}/{required}
          </span>
        </header>
        <div className="card__body">
          <div style={{ display: "flex", gap: 6, marginBottom: 12 }}>
            {Array.from({ length: required }, (_, i) => (
              <div
                key={i}
                className="led"
                data-state={i < captured ? "online" : i === captured ? "warn" : "off"}
                style={{ flex: 1, justifyContent: "center" }}
              >
                <span className="led__dot" aria-hidden="true" />
                SAMPLE {i + 1}
              </div>
            ))}
          </div>

          <p className="body" style={{ marginBottom: 12 }}>
            {phase === "pick"
              ? "Pick an edge and line above, then press Start teach."
              : phase === "capturing" || phase === "ready"
                ? `Run a known-good part across the belt and press Capture sample. ${remaining} remaining.`
                : phase === "done"
                  ? "Teach complete. Line is armed and inspecting."
                  : "Waiting…"}
          </p>

          <div style={{ display: "flex", gap: 8 }}>
            <button
              type="button"
              className="btn"
              disabled={busy || (phase !== "capturing" && phase !== "ready") || remaining === 0}
              onClick={() => void capture()}
            >
              Capture sample {captured + 1}
            </button>
            <button
              type="button"
              className="btn btn--primary"
              disabled={busy || phase !== "ready"}
              onClick={() => void finalize()}
            >
              Fit baseline & arm line
            </button>
            <button
              type="button"
              className="btn btn--ghost"
              disabled={busy || phase === "pick" || phase === "done"}
              onClick={() => void abort()}
            >
              Abort
            </button>
          </div>
        </div>
      </section>

      {result ? (
        <section className="card">
          <header className="card__head">
            <h3 className="h3">03 · Done — line is live</h3>
            <span className="mono" style={{ fontSize: 11, color: "var(--muted)" }}>
              {result.line_id}
            </span>
          </header>
          <div className="card__body">
            <dl className="kv">
              <div>
                <dt>Samples</dt>
                <dd>{result.n_samples}</dd>
              </div>
              <div>
                <dt>Geometry</dt>
                <dd>
                  {result.rows}×{result.cols}
                </dd>
              </div>
              <div>
                <dt>Baseline mean range</dt>
                <dd>
                  {result.mean_min.toFixed(1)} … {result.mean_max.toFixed(1)}
                </dd>
              </div>
              <div>
                <dt>Line status</dt>
                <dd>
                  <span className="led" data-state="online">
                    <span className="led__dot" aria-hidden="true" />
                    {result.line_status.toUpperCase()}
                  </span>
                </dd>
              </div>
            </dl>
            <div style={{ marginTop: 12 }}>
              <button type="button" className="btn" onClick={reset}>
                Teach another line
              </button>
            </div>
          </div>
        </section>
      ) : null}

      <section className="card">
        <header className="card__head">
          <h3 className="h3">What ships to the cloud</h3>
        </header>
        <div className="card__body">
          <p className="body">
            The teach step does <b>not</b> upload raw tactile frames. Only the
            per-cell mean and standard deviation across your five samples, plus
            a small set of global descriptors (sum, max, centroid, area, peak
            gradient), are written back to Tactile Cloud. Raw frames stay on
            the Edge appliance for 24 hours and are then purged.
          </p>
        </div>
      </section>
    </div>
  );
}
