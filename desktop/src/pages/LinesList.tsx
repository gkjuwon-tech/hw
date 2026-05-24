/**
 * Lines list page.
 *
 * Inventory of every conveyor line registered to the current org. The
 * heavy lifting of polling lives in `App.tsx`; this component is pure
 * presentation + click-to-open.
 */

import { PageHeader } from "../components/PageHeader";
import type { Line, LineStatus } from "../lib/types";

export interface LinesListProps {
  lines: Line[];
  onOpen: (lineId: string) => void;
  apiError: boolean;
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toISOString().slice(0, 10);
  } catch {
    return iso.slice(0, 10);
  }
}

function ledStateFor(status: LineStatus | undefined): string {
  const s = status ?? "uncalibrated";
  if (s === "live") return "online";
  if (s === "error") return "bad";
  if (s === "uncalibrated") return "warn";
  return "off";
}

export function LinesList({ lines, onOpen, apiError }: LinesListProps): JSX.Element {
  return (
    <div className="page">
      <PageHeader
        eyebrow="LINES"
        title="Conveyor inventory"
        lede="One row per conveyor segment. Status reflects the line's last reported state from its assigned Edge appliance."
      />

      {apiError ? (
        <div className="banner">
          <b>SIDECAR DOWN.</b>&nbsp;The list below may be stale.
        </div>
      ) : null}

      <section className="card">
        <header className="card__head">
          <h3 className="h3">Lines</h3>
          <span className="mono" style={{ fontSize: 11, color: "var(--muted)" }}>
            {lines.length} total
          </span>
        </header>
        <div className="card__body" style={{ padding: 0 }}>
          {lines.length === 0 ? (
            <div className="empty">No lines registered.</div>
          ) : (
            <table className="datagrid">
              <thead>
                <tr>
                  <th>Line ID</th>
                  <th>Customer tag</th>
                  <th>Mesh</th>
                  <th>Status</th>
                  <th className="right">Score</th>
                  <th className="right">Drift (z)</th>
                  <th>Registered</th>
                </tr>
              </thead>
              <tbody>
                {lines.map((line) => {
                  const s = line.status ?? "uncalibrated";
                  return (
                    <tr
                      key={line.id}
                      className="is-clickable"
                      onClick={() => onOpen(line.id)}
                    >
                      <td className="id">{line.id}</td>
                      <td>{line.customer_tag}</td>
                      <td>
                        {line.rows}×{line.cols}
                      </td>
                      <td>
                        <span className="led" data-state={ledStateFor(line.status)}>
                          <span className="led__dot" aria-hidden="true" />
                          {s.toUpperCase()}
                        </span>
                      </td>
                      <td className="right">
                        {line.recent_score !== null && line.recent_score !== undefined
                          ? line.recent_score.toFixed(3)
                          : "—"}
                      </td>
                      <td className="right">
                        {line.drift_z !== null && line.drift_z !== undefined
                          ? line.drift_z.toFixed(2)
                          : "—"}
                      </td>
                      <td>{formatDate(line.created_at)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </section>
    </div>
  );
}
