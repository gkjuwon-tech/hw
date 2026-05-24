/**
 * Sidebar device tree.
 *
 * Three collapsible groups — Edges, Lines, Mesh segments — each
 * listing the live inventory pulled from the sidecar. Selecting a
 * row navigates the content pane to the corresponding detail page.
 *
 * Status LED column on the right uses the global `.led[data-state]`
 * vocabulary so the indicator color matches the page-level status.
 */

import { useState } from "react";
import type { Edge, Line, MeshSegment } from "../lib/types";

export interface DeviceTreeProps {
  edges: Edge[];
  lines: Line[];
  meshes: MeshSegment[];
  selection:
    | { kind: "edge"; id: string }
    | { kind: "line"; id: string }
    | { kind: "mesh"; id: string }
    | null;
  onSelectEdge: (id: string) => void;
  onSelectLine: (id: string) => void;
  onSelectMesh: (id: string) => void;
}

type GroupKey = "edges" | "lines" | "meshes";

export function DeviceTree(props: DeviceTreeProps): JSX.Element {
  const { edges, lines, meshes, selection } = props;
  const [open, setOpen] = useState<Record<GroupKey, boolean>>({
    edges: true,
    lines: true,
    meshes: true,
  });

  const toggle = (key: GroupKey): void =>
    setOpen((prev) => ({ ...prev, [key]: !prev[key] }));

  return (
    <div className="devicetree" role="tree" aria-label="Devices">
      <div className="devicetree__group">
        <button
          type="button"
          className="devicetree__grouphead"
          onClick={() => toggle("edges")}
          aria-expanded={open.edges}
        >
          <span className="twirl">{open.edges ? "▼" : "▶"}</span>
          EDGES
          <span className="count mono">{edges.length}</span>
        </button>
        {open.edges &&
          (edges.length === 0 ? (
            <div className="devicetree__row" aria-disabled="true">
              <span className="led" data-state="offline">
                <span className="led__dot" aria-hidden="true" />
              </span>
              <span className="label" style={{ color: "var(--muted)" }}>
                no edges enrolled
              </span>
            </div>
          ) : (
            edges.map((e) => {
              const selected =
                selection?.kind === "edge" && selection.id === e.id;
              return (
                <button
                  key={e.id}
                  type="button"
                  className="devicetree__row"
                  aria-current={selected ? "true" : undefined}
                  onClick={() => props.onSelectEdge(e.id)}
                >
                  <span className="led" data-state={e.status}>
                    <span className="led__dot" aria-hidden="true" />
                  </span>
                  <span className="label">{e.hostname || e.id}</span>
                  <span className="badge">{e.model.replace("jetson-", "")}</span>
                </button>
              );
            })
          ))}
      </div>

      <div className="devicetree__group">
        <button
          type="button"
          className="devicetree__grouphead"
          onClick={() => toggle("lines")}
          aria-expanded={open.lines}
        >
          <span className="twirl">{open.lines ? "▼" : "▶"}</span>
          LINES
          <span className="count mono">{lines.length}</span>
        </button>
        {open.lines &&
          (lines.length === 0 ? (
            <div className="devicetree__row" aria-disabled="true">
              <span className="led" data-state="offline">
                <span className="led__dot" aria-hidden="true" />
              </span>
              <span className="label" style={{ color: "var(--muted)" }}>
                no lines registered
              </span>
            </div>
          ) : (
            lines.map((line) => {
              const selected =
                selection?.kind === "line" && selection.id === line.id;
              const state = line.status ?? "uncalibrated";
              const ledState =
                state === "live"
                  ? "online"
                  : state === "error"
                    ? "bad"
                    : state === "uncalibrated"
                      ? "warn"
                      : "off";
              return (
                <button
                  key={line.id}
                  type="button"
                  className="devicetree__row"
                  aria-current={selected ? "true" : undefined}
                  onClick={() => props.onSelectLine(line.id)}
                >
                  <span className="led" data-state={ledState}>
                    <span className="led__dot" aria-hidden="true" />
                  </span>
                  <span className="label">{line.id}</span>
                  <span className="badge">
                    {line.rows}×{line.cols}
                  </span>
                </button>
              );
            })
          ))}
      </div>

      <div className="devicetree__group">
        <button
          type="button"
          className="devicetree__grouphead"
          onClick={() => toggle("meshes")}
          aria-expanded={open.meshes}
        >
          <span className="twirl">{open.meshes ? "▼" : "▶"}</span>
          MESH SEGMENTS
          <span className="count mono">{meshes.length}</span>
        </button>
        {open.meshes &&
          (meshes.length === 0 ? (
            <div className="devicetree__row" aria-disabled="true">
              <span className="led" data-state="offline">
                <span className="led__dot" aria-hidden="true" />
              </span>
              <span className="label" style={{ color: "var(--muted)" }}>
                no mesh installed
              </span>
            </div>
          ) : (
            meshes.map((m) => {
              const selected =
                selection?.kind === "mesh" && selection.id === m.id;
              const state =
                m.health_pct >= 95 ? "good" : m.health_pct >= 80 ? "warn" : "bad";
              return (
                <button
                  key={m.id}
                  type="button"
                  className="devicetree__row"
                  aria-current={selected ? "true" : undefined}
                  onClick={() => props.onSelectMesh(m.id)}
                >
                  <span className="led" data-state={state}>
                    <span className="led__dot" aria-hidden="true" />
                  </span>
                  <span className="label">{m.id}</span>
                  <span className="badge">{m.roll_lot || "—"}</span>
                </button>
              );
            })
          ))}
      </div>
    </div>
  );
}
