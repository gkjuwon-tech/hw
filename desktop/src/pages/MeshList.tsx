/**
 * Mesh segments page.
 *
 * Inventory of every roll-mesh piece installed across this org's
 * lines. Each row is one installed segment with its geometry, health,
 * and the edge box that currently reads it.
 */

import { PageHeader } from "../components/PageHeader";
import type { Edge, Line, MeshSegment } from "../lib/types";

export interface MeshListProps {
  meshes: MeshSegment[];
  lines: Line[];
  edges: Edge[];
}

function healthState(pct: number): "good" | "warn" | "bad" {
  if (pct >= 95) return "good";
  if (pct >= 80) return "warn";
  return "bad";
}

function daysSince(iso: string): number {
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return 0;
  return Math.max(0, Math.floor((Date.now() - t) / 86_400_000));
}

export function MeshList({ meshes, lines, edges }: MeshListProps): JSX.Element {
  const lineById = new Map(lines.map((l) => [l.id, l]));
  const edgeById = new Map(edges.map((e) => [e.id, e]));

  return (
    <div className="page">
      <PageHeader
        eyebrow="MESH"
        title="Tactile Mesh segments"
        lede="Each row is one piece of the Tactile Mesh roll, glued to a specific conveyor. Health is computed from per-cell drift relative to the calibration baseline."
      />

      <section className="card">
        <header className="card__head">
          <h3 className="h3">Installed segments</h3>
          <span className="mono" style={{ fontSize: 11, color: "var(--muted)" }}>
            {meshes.length} total
          </span>
        </header>
        <div className="card__body" style={{ padding: 0 }}>
          {meshes.length === 0 ? (
            <div className="empty">No mesh segments installed.</div>
          ) : (
            <table className="datagrid">
              <thead>
                <tr>
                  <th>Segment ID</th>
                  <th>Line</th>
                  <th>Edge</th>
                  <th>Roll lot</th>
                  <th className="right">Width (mm)</th>
                  <th className="right">Length (mm)</th>
                  <th className="right">Geometry</th>
                  <th>Installed</th>
                  <th className="right">Age (d)</th>
                  <th className="right">Health (%)</th>
                  <th className="right">Dead cells</th>
                </tr>
              </thead>
              <tbody>
                {meshes.map((m) => {
                  const line = lineById.get(m.line_id);
                  const edge = m.edge_id ? edgeById.get(m.edge_id) : null;
                  return (
                    <tr key={m.id}>
                      <td className="id">{m.id}</td>
                      <td>
                        {line ? (
                          <>
                            <span className="id">{line.id}</span>
                            <span style={{ color: "var(--muted)" }}> · {line.customer_tag}</span>
                          </>
                        ) : (
                          m.line_id
                        )}
                      </td>
                      <td>{edge ? edge.hostname || edge.id : m.edge_id ?? "—"}</td>
                      <td>{m.roll_lot || "—"}</td>
                      <td className="right">{m.belt_width_mm || "—"}</td>
                      <td className="right">{m.length_mm || "—"}</td>
                      <td className="right">
                        {m.rows}×{m.cols}
                      </td>
                      <td>{m.installed_at.slice(0, 10)}</td>
                      <td className="right">{daysSince(m.installed_at)}</td>
                      <td className="right">
                        <span className="led" data-state={healthState(m.health_pct)}>
                          <span className="led__dot" aria-hidden="true" />
                          {m.health_pct.toFixed(1)}
                        </span>
                      </td>
                      <td className="right">{m.dead_cells}</td>
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
