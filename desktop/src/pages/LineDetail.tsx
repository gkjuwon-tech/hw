import { useEffect, useState } from "react";
import { PageHeader } from "../components/PageHeader";
import { Heatmap } from "../components/Heatmap";
import { Spark } from "../components/Spark";
import { KV } from "../components/KV";
import { api } from "../lib/api";
import { subscribeLineEvents } from "../lib/sse";
import type { InspectionEvent, Line } from "../lib/types";

export interface LineDetailProps {
  lineId: string;
  onBack: () => void;
}

const MAX_HISTORY = 240;

export function LineDetail({ lineId, onBack }: LineDetailProps): JSX.Element {
  const [line, setLine] = useState<Line | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [latest, setLatest] = useState<InspectionEvent | null>(null);
  const [history, setHistory] = useState<number[]>([]);

  useEffect(() => {
    let cancelled = false;
    setLine(null);
    setErr(null);
    setLatest(null);
    setHistory([]);

    api
      .getLine(lineId)
      .then((row) => {
        if (cancelled) return;
        setLine(row);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setErr(e instanceof Error ? e.message : String(e));
      });

    let sub: { close: () => void } | null = null;
    void subscribeLineEvents(
      lineId,
      (ev) => {
        setLatest(ev);
        setHistory((prev) => {
          const next = prev.concat(ev.score);
          if (next.length > MAX_HISTORY) next.shift();
          return next;
        });
      },
      () => {},
    ).then((s) => {
      if (cancelled) {
        s.close();
        return;
      }
      sub = s;
    });

    return () => {
      cancelled = true;
      sub?.close();
    };
  }, [lineId]);

  const rows = line?.rows ?? 16;
  const cols = line?.cols ?? 16;

  return (
    <div className="page">
      <PageHeader
        eyebrow={`Line · ${lineId}`}
        title={line?.customer_tag ?? "Loading line…"}
        lede={
          err
            ? `Could not load line: ${err}`
            : `Live tactile heatmap and rolling anomaly score, streamed from the sidecar over SSE. Each frame represents one part passing under the mesh.`
        }
        actions={
          <button type="button" className="btn btn--ghost" onClick={onBack}>
            ← Back to lines
          </button>
        }
      />

      <div className="grid grid--detail" style={{ marginTop: "2rem" }}>
        <section className="heatmap-card">
          <div>
            <p className="eyebrow eyebrow--light">
              <span className="eyebrow__dot" aria-hidden="true" />
              Live tactile field
            </p>
            <h2 className="h3">{rows}×{cols} pressure mesh</h2>
          </div>
          <Heatmap grid={latest?.heatmap ?? null} rows={rows} cols={cols} />
          <div className="meta">
            <span>
              SCORE <b className="mono">{latest ? latest.score.toFixed(3) : "—"}</b>
            </span>
            <span>
              DRIFT <b className="mono">{latest?.drift_z != null ? latest.drift_z.toFixed(2) : "—"}</b>
            </span>
            <span>
              VERDICT{" "}
              <b className="mono">
                {latest ? (latest.passed ? "PASS" : "REJECT") : "—"}
              </b>
            </span>
          </div>
        </section>

        <section className="card">
          <p className="eyebrow">
            <span className="eyebrow__dot" aria-hidden="true" />
            Anomaly score
          </p>
          <h3 className="h3" style={{ marginTop: "0.5rem" }}>
            Rolling window
          </h3>
          <div style={{ marginTop: "1rem" }}>
            <Spark values={history} threshold={1.0} />
          </div>
          <KV
            rows={[
              { k: "Customer tag", v: line?.customer_tag ?? "—" },
              { k: "Mesh geometry", v: `${rows} × ${cols}` },
              { k: "Registered", v: line?.created_at?.slice(0, 10) ?? "—" },
              {
                k: "Recent score",
                v: line?.recent_score?.toFixed(3) ?? "—",
              },
              {
                k: "Drift (z)",
                v: line?.drift_z != null ? line.drift_z.toFixed(2) : "—",
              },
            ]}
          />
        </section>
      </div>
    </div>
  );
}
