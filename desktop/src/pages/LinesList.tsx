import { useEffect, useState } from "react";
import { PageHeader } from "../components/PageHeader";
import { api } from "../lib/api";
import type { Line } from "../lib/types";

export interface LinesListProps {
  onOpen: (lineId: string) => void;
  onCountChange: (n: number) => void;
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toISOString().slice(0, 10);
  } catch {
    return iso.slice(0, 10);
  }
}

export function LinesList({ onOpen, onCountChange }: LinesListProps): JSX.Element {
  const [lines, setLines] = useState<Line[] | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .listLines()
      .then((rows) => {
        if (cancelled) return;
        setLines(rows);
        onCountChange(rows.length);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setErr(e instanceof Error ? e.message : String(e));
        setLines([]);
        onCountChange(0);
      });
    return () => {
      cancelled = true;
    };
  }, [onCountChange]);

  return (
    <div className="page">
      <PageHeader
        eyebrow="01 — Lines"
        title="Every part on the line, scored."
        lede="One row per conveyor segment. Click a line to open its live tactile dashboard, drift, and last 24 hours of inspections."
        actions={
          <>
            <button type="button" className="btn btn--ghost">
              Filter
            </button>
            <button type="button" className="btn btn--primary">
              Register a line
            </button>
          </>
        }
      />

      {err && lines !== null && lines.length === 0 ? (
        <div className="empty">
          <p className="eyebrow">
            <span className="eyebrow__dot" aria-hidden="true" />
            No data yet
          </p>
          <p className="body" style={{ marginInline: "auto" }}>
            The sidecar responded but no lines are registered for this
            organization. Add the first line via <code className="mono">POST /v1/lines</code> or
            the {`"`}Register a line{`"`} button.
          </p>
          <p className="mono" style={{ marginTop: "1rem", fontSize: "0.8rem", color: "var(--muted-2)" }}>
            {err}
          </p>
        </div>
      ) : (
        <table className="lines-table">
          <thead>
            <tr>
              <th>Line ID</th>
              <th>Customer tag</th>
              <th>Mesh</th>
              <th>Status</th>
              <th>Registered</th>
            </tr>
          </thead>
          <tbody>
            {(lines ?? []).map((line) => (
              <tr key={line.id} onClick={() => onOpen(line.id)}>
                <td className="id">{line.id}</td>
                <td>{line.customer_tag}</td>
                <td className="mono">
                  {line.rows}×{line.cols}
                </td>
                <td>
                  <span className="status-dot" data-state={line.status ?? "uncalibrated"}>
                    <span className="d" aria-hidden="true" />
                    {(line.status ?? "uncalibrated").toUpperCase()}
                  </span>
                </td>
                <td className="mono">{formatDate(line.created_at)}</td>
              </tr>
            ))}
            {lines !== null && lines.length === 0 && !err ? (
              <tr>
                <td colSpan={5} style={{ textAlign: "center", padding: "2rem", color: "var(--muted)" }}>
                  No lines registered yet.
                </td>
              </tr>
            ) : null}
            {lines === null ? (
              <tr>
                <td colSpan={5} style={{ textAlign: "center", padding: "2rem", color: "var(--muted)" }}>
                  Loading…
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      )}
    </div>
  );
}
