/**
 * Overview — landing screen.
 *
 * Shows the fleet at a glance: counts, edge status table, line status
 * table. Clicking through into either table opens the corresponding
 * detail page. Deliberately no charts or hero copy — that's the
 * landing-page-website's job, not the operator client's.
 */

import { useMemo } from "react";
import { PageHeader } from "../components/PageHeader";
import type { Edge, Line, MeshSegment } from "../lib/types";

export interface OverviewProps {
  edges: Edge[];
  lines: Line[];
  meshes: MeshSegment[];
  apiStatus: "ok" | "boot" | "down";
  onOpenEdge: (id: string) => void;
  onOpenLine: (id: string) => void;
}

function countBy<T, K extends string>(rows: T[], pick: (t: T) => K): Record<K, number> {
  const out: Record<string, number> = {};
  for (const r of rows) {
    const k = pick(r);
    out[k] = (out[k] ?? 0) + 1;
  }
  return out as Record<K, number>;
}

export function Overview({
  edges,
  lines,
  meshes,
  apiStatus,
  onOpenEdge,
  onOpenLine,
}: OverviewProps): JSX.Element {
  const edgeStates = useMemo(() => countBy(edges, (e) => e.status), [edges]);
  const lineStates = useMemo(
    () => countBy(lines, (l) => (l.status ?? "uncalibrated") as Line["status"] & string),
    [lines],
  );

  return (
    <div className="page">
      <PageHeader
        eyebrow="OVERVIEW"
        title="Tactile Cloud · operator console"
        actions={
          <span className="led" data-state={apiStatus === "ok" ? "online" : apiStatus}>
            <span className="led__dot" aria-hidden="true" />
            API {apiStatus === "ok" ? "CONNECTED" : apiStatus.toUpperCase()}
          </span>
        }
      />

      {apiStatus === "down" ? (
        <div className="banner">
          <b>SIDECAR DOWN.</b>&nbsp;The local FastAPI service is unreachable.
          Inventory shown below is the last cached snapshot.
        </div>
      ) : null}

      <div className="grid grid--3">
        <Tile
          label="Edges"
          value={edges.length}
          breakdown={[
            ["online", edgeStates.online ?? 0],
            ["degraded", edgeStates.degraded ?? 0],
            ["offline", edgeStates.offline ?? 0],
          ]}
        />
        <Tile
          label="Lines"
          value={lines.length}
          breakdown={[
            ["live", lineStates.live ?? 0],
            ["uncalibrated", lineStates.uncalibrated ?? 0],
            ["error", lineStates.error ?? 0],
          ]}
        />
        <Tile
          label="Mesh segments"
          value={meshes.length}
          breakdown={[
            ["healthy", meshes.filter((m) => m.health_pct >= 95).length],
            ["degraded", meshes.filter((m) => m.health_pct < 95 && m.health_pct >= 80).length],
            ["failing", meshes.filter((m) => m.health_pct < 80).length],
          ]}
        />
      </div>

      <div className="grid grid--detail">
        <section className="card">
          <header className="card__head">
            <h3 className="h3">Edges</h3>
            <span className="mono" style={{ fontSize: 11, color: "var(--muted)" }}>
              {edges.length} total
            </span>
          </header>
          <div className="card__body" style={{ padding: 0, overflow: "auto", maxHeight: 320 }}>
            {edges.length === 0 ? (
              <div className="empty">No edge appliances enrolled yet.</div>
            ) : (
              <table className="datagrid">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Hostname</th>
                    <th>Status</th>
                    <th className="right">GPU °C</th>
                    <th className="right">FPS</th>
                  </tr>
                </thead>
                <tbody>
                  {edges.map((e) => (
                    <tr
                      key={e.id}
                      className="is-clickable"
                      onClick={() => onOpenEdge(e.id)}
                    >
                      <td className="id">{e.id}</td>
                      <td>{e.hostname || "—"}</td>
                      <td>
                        <span className="led" data-state={e.status}>
                          <span className="led__dot" aria-hidden="true" />
                          {e.status.toUpperCase()}
                        </span>
                      </td>
                      <td className="right">{e.gpu_temp_c.toFixed(1)}</td>
                      <td className="right">{e.frames_per_second.toFixed(1)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </section>

        <section className="card">
          <header className="card__head">
            <h3 className="h3">Lines</h3>
            <span className="mono" style={{ fontSize: 11, color: "var(--muted)" }}>
              {lines.length} total
            </span>
          </header>
          <div className="card__body" style={{ padding: 0, overflow: "auto", maxHeight: 320 }}>
            {lines.length === 0 ? (
              <div className="empty">No lines registered.</div>
            ) : (
              <table className="datagrid">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Tag</th>
                    <th>Mesh</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {lines.map((l) => {
                    const s = (l.status ?? "uncalibrated") as string;
                    const ledState =
                      s === "live"
                        ? "online"
                        : s === "error"
                          ? "bad"
                          : s === "uncalibrated"
                            ? "warn"
                            : "off";
                    return (
                      <tr
                        key={l.id}
                        className="is-clickable"
                        onClick={() => onOpenLine(l.id)}
                      >
                        <td className="id">{l.id}</td>
                        <td>{l.customer_tag}</td>
                        <td>
                          {l.rows}×{l.cols}
                        </td>
                        <td>
                          <span className="led" data-state={ledState}>
                            <span className="led__dot" aria-hidden="true" />
                            {s.toUpperCase()}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}

interface TileProps {
  label: string;
  value: number;
  breakdown: ReadonlyArray<readonly [string, number]>;
}

function Tile({ label, value, breakdown }: TileProps): JSX.Element {
  return (
    <div className="card">
      <header className="card__head">
        <h3 className="h3">{label}</h3>
      </header>
      <div className="card__body" style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: 12, alignItems: "center" }}>
        <span className="num">{value}</span>
        <dl style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: "2px 8px", fontSize: 11 }}>
          {breakdown.map(([k, v]) => (
            <div
              key={k}
              style={{ display: "contents" }}
            >
              <dt
                style={{
                  textTransform: "uppercase",
                  letterSpacing: "0.08em",
                  fontWeight: 700,
                  color: "var(--muted)",
                }}
              >
                {k}
              </dt>
              <dd className="mono" style={{ textAlign: "right" }}>
                {v}
              </dd>
            </div>
          ))}
        </dl>
      </div>
    </div>
  );
}
