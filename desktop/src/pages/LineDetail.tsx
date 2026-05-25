/**
 * Line detail page.
 *
 * Live tactile heatmap + rolling anomaly score for one conveyor
 * segment. The renderer subscribes to `/v1/lines/{id}/events` over SSE
 * and replays the in-memory ring buffer on connect.
 */

import { useEffect, useRef, useState } from "react";
import { PageHeader } from "../components/PageHeader";
import { Heatmap } from "../components/Heatmap";
import { Spark } from "../components/Spark";
import { api } from "../lib/api";
import { subscribeLineEvents, type Subscription } from "../lib/sse";
import type { InspectionEvent, Line } from "../lib/types";

export interface LineDetailProps {
  lineId: string;
  onBack: () => void;
}

const MAX_HISTORY = 240;

export function LineDetail({ lineId, onBack }: LineDetailProps): JSX.Element {
  const [line, setLine] = useState<Line | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [sseLive, setSseLive] = useState(false);
  const [latest, setLatest] = useState<InspectionEvent | null>(null);
  const [history, setHistory] = useState<number[]>([]);
  const [recent, setRecent] = useState<InspectionEvent[]>([]);
  const subRef = useRef<Subscription | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLine(null);
    setErr(null);
    setLatest(null);
    setHistory([]);
    setRecent([]);
    setSseLive(false);

    void api
      .getLine(lineId)
      .then((row) => {
        if (cancelled) return;
        setLine(row);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setErr(e instanceof Error ? e.message : String(e));
      });

    void api
      .recentEvents(lineId)
      .then((rows) => {
        if (cancelled) return;
        setRecent(rows.slice(-32).reverse());
        setHistory(rows.map((r) => r.score));
        if (rows.length > 0) setLatest(rows[rows.length - 1] ?? null);
      })
      .catch(() => {});

    void subscribeLineEvents(
      lineId,
      (ev) => {
        setLatest(ev);
        setHistory((prev) => {
          const next = prev.concat(ev.score);
          if (next.length > MAX_HISTORY) next.shift();
          return next;
        });
        setRecent((prev) => {
          const next = [ev, ...prev];
          if (next.length > 32) next.pop();
          return next;
        });
      },
      () => setSseLive(false),
    ).then((s) => {
      if (cancelled) {
        s.close();
        return;
      }
      subRef.current = s;
      setSseLive(true);
    });

    return () => {
      cancelled = true;
      subRef.current?.close();
      subRef.current = null;
    };
  }, [lineId]);

  const rows = line?.rows ?? 16;
  const cols = line?.cols ?? 16;

  return (
    <div className="page">
      <PageHeader
        eyebrow={`LINE · ${lineId}`}
        title={line?.customer_tag ?? "Loading…"}
        actions={
          <>
            <span className="led" data-state={sseLive ? "online" : "warn"}>
              <span className="led__dot" aria-hidden="true" />
              {sseLive ? "STREAMING" : "POLLING"}
            </span>
            <button type="button" className="btn" onClick={onBack}>
              ← Back
            </button>
          </>
        }
      />

      {err ? (
        <div className="banner">
          <b>ERR</b>&nbsp;{err}
        </div>
      ) : null}

      <div className="grid grid--detail">
        <section className="card card--ink heatmap-card">
          <header className="card__head">
            <h3 className="h3">Live tactile field</h3>
            <span className="mono" style={{ fontSize: 11, color: "rgba(255,255,255,0.7)" }}>
              {rows}×{cols} mesh
            </span>
          </header>
          <div className="card__body">
            <Heatmap grid={latest?.heatmap ?? null} rows={rows} cols={cols} />
          </div>
          <div className="meta">
            <span>
              SCORE&nbsp;<b>{latest ? latest.score.toFixed(3) : "—"}</b>
            </span>
            <span>
              DRIFT&nbsp;
              <b>{latest?.drift_z != null ? latest.drift_z.toFixed(2) : "—"}</b>
            </span>
            <span>
              VERDICT&nbsp;
              <b style={{ color: latest ? (latest.passed ? "var(--signal-good)" : "var(--signal-bad)") : "inherit" }}>
                {latest ? (latest.passed ? "PASS" : "REJECT") : "—"}
              </b>
            </span>
          </div>
        </section>

        <section className="card">
          <header className="card__head">
            <h3 className="h3">Anomaly score</h3>
            <span className="mono" style={{ fontSize: 11, color: "var(--muted)" }}>
              {history.length} pts
            </span>
          </header>
          <div className="card__body">
            <Spark values={history} threshold={1.0} />
            <dl className="kv" style={{ marginTop: 8 }}>
              <div>
                <dt>Customer tag</dt>
                <dd>{line?.customer_tag ?? "—"}</dd>
              </div>
              <div>
                <dt>Mesh geometry</dt>
                <dd>
                  {rows} × {cols}
                </dd>
              </div>
              <div>
                <dt>Registered</dt>
                <dd>{line?.created_at?.slice(0, 10) ?? "—"}</dd>
              </div>
              <div>
                <dt>Recent score</dt>
                <dd>{line?.recent_score?.toFixed(3) ?? "—"}</dd>
              </div>
              <div>
                <dt>Drift (z)</dt>
                <dd>{line?.drift_z != null ? line.drift_z.toFixed(2) : "—"}</dd>
              </div>
            </dl>
          </div>
        </section>
      </div>

      <section className="card">
        <header className="card__head">
          <h3 className="h3">Recent inspections</h3>
          <span className="mono" style={{ fontSize: 11, color: "var(--muted)" }}>
            {recent.length} events
          </span>
        </header>
        <div className="card__body" style={{ padding: 0, maxHeight: 260, overflow: "auto" }}>
          {recent.length === 0 ? (
            <div className="empty">No inspections yet on this line.</div>
          ) : (
            <table className="datagrid">
              <thead>
                <tr>
                  <th>Timestamp</th>
                  <th className="right">Score</th>
                  <th className="right">Drift (z)</th>
                  <th>Verdict</th>
                </tr>
              </thead>
              <tbody>
                {recent.map((ev, i) => (
                  <tr key={`${ev.ts}-${i}`}>
                    <td>{ev.ts.slice(0, 19).replace("T", " ")}</td>
                    <td className="right">{ev.score.toFixed(3)}</td>
                    <td className="right">{ev.drift_z != null ? ev.drift_z.toFixed(2) : "—"}</td>
                    <td>
                      <span className="led" data-state={ev.passed ? "pass" : "fail"}>
                        <span className="led__dot" aria-hidden="true" />
                        {ev.passed ? "PASS" : "REJECT"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>
    </div>
  );
}
