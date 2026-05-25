/**
 * Mesh Fabric console.
 *
 * Operator view of the edge-to-edge mesh topology. Shows every edge
 * that has announced into the fabric within the last 30s, its spare
 * capacity, and peer-to-peer latencies.
 *
 * Failover: pick a source edge + a line + a target edge and reassign
 * the line. Backend validates capacity + liveness.
 */

import { useEffect, useState } from "react";

import { PageHeader } from "../components/PageHeader";
import { api } from "../lib/api";
import type {
  ApiError,
  Edge,
  Line,
  MeshPeer,
  MeshSegment,
  MeshTopology,
} from "../lib/types";

export interface MeshFabricProps {
  edges: Edge[];
  lines: Line[];
  meshes: MeshSegment[];
  onRefresh: () => Promise<void>;
}

const POLL_MS = 4_000;

export function MeshFabric({ edges, lines, meshes, onRefresh }: MeshFabricProps): JSX.Element {
  const [topology, setTopology] = useState<MeshTopology | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const [source, setSource] = useState("");
  const [target, setTarget] = useState("");
  const [lineId, setLineId] = useState("");

  const refresh = async (): Promise<void> => {
    setErr(null);
    try {
      const t = await api.meshTopology();
      setTopology(t);
    } catch (e) {
      setErr((e as ApiError).message);
    }
  };

  useEffect(() => {
    void refresh();
    const id = window.setInterval(() => void refresh(), POLL_MS);
    return () => window.clearInterval(id);
  }, []);

  const failover = async (): Promise<void> => {
    setBusy(true);
    setErr(null);
    setMsg(null);
    try {
      const r = await api.meshFailover({
        source_edge_id: source,
        target_edge_id: target,
        line_id: lineId,
      });
      setMsg(`Line ${r.line_id} reassigned: ${r.old_edge_id} → ${r.new_edge_id}`);
      await refresh();
      await onRefresh();
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  };

  const enrolledMap = new Map<string, Edge>(edges.map((e) => [e.id, e]));
  const linesForSource = meshes.filter((m) => m.edge_id === source);

  return (
    <div className="page">
      <PageHeader
        eyebrow="MESH FABRIC"
        title="Edge-to-edge gossip topology"
        lede="Edges that have announced into the fabric within the last 30 seconds. The cloud is the authoritative graph; the agents gossip via /v1/mesh/announce."
        actions={
          <button type="button" className="btn" onClick={() => void refresh()}>
            Refresh
          </button>
        }
      />

      {err ? (
        <div className="banner">
          <b>ERR</b>&nbsp;{err}
        </div>
      ) : null}

      <section className="card">
        <header className="card__head">
          <h3 className="h3">Topology</h3>
          <span className="mono" style={{ fontSize: 11, color: "var(--muted)" }}>
            {topology
              ? `${topology.alive_count}/${topology.edges_count} alive`
              : "loading…"}
          </span>
        </header>
        <div className="card__body" style={{ padding: 0 }}>
          {topology && topology.nodes.length > 0 ? (
            <table className="datagrid">
              <thead>
                <tr>
                  <th>Edge ID</th>
                  <th>Hostname</th>
                  <th>IP</th>
                  <th>Port</th>
                  <th>Status</th>
                  <th className="right">Capacity free</th>
                  <th className="right">Last announce</th>
                  <th className="right">Peers</th>
                  <th className="right">Median peer RTT</th>
                </tr>
              </thead>
              <tbody>
                {topology.nodes.map((n: MeshPeer) => {
                  const e = enrolledMap.get(n.edge_id);
                  const latencies = Object.values(n.latency_ms);
                  const median = latencies.length
                    ? [...latencies].sort((a, b) => a - b)[Math.floor(latencies.length / 2)]
                    : null;
                  return (
                    <tr key={n.edge_id}>
                      <td className="id">{n.edge_id}</td>
                      <td>{e?.hostname ?? "—"}</td>
                      <td className="mono">{n.ip}</td>
                      <td className="mono">{n.port}</td>
                      <td>
                        <span className="led" data-state={n.alive ? "online" : "off"}>
                          <span className="led__dot" aria-hidden="true" />
                          {n.alive ? "ALIVE" : "STALE"}
                        </span>
                      </td>
                      <td className="right">{n.capacity_free_pct.toFixed(0)} %</td>
                      <td className="right">{n.last_announce_ago_s.toFixed(1)} s</td>
                      <td className="right">{Object.keys(n.latency_ms).length}</td>
                      <td className="right">{median != null ? `${median.toFixed(1)} ms` : "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          ) : (
            <div className="empty">
              No edges in the fabric yet. Start the edge_agent on a Jetson to
              see it announce.
            </div>
          )}
        </div>
      </section>

      <section className="card">
        <header className="card__head">
          <h3 className="h3">Failover</h3>
          <span className="mono" style={{ fontSize: 11, color: "var(--muted)" }}>
            POST /v1/mesh/failover
          </span>
        </header>
        <div
          className="card__body"
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr 1fr auto",
            gap: 8,
            alignItems: "end",
          }}
        >
          <label className="field">
            <span>SOURCE EDGE</span>
            <select
              className="mono"
              value={source}
              onChange={(e) => {
                setSource(e.target.value);
                setLineId("");
              }}
              disabled={busy}
            >
              <option value="">— choose —</option>
              {edges.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.id} ({e.status})
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>LINE</span>
            <select
              className="mono"
              value={lineId}
              onChange={(e) => setLineId(e.target.value)}
              disabled={busy || !source}
            >
              <option value="">— choose —</option>
              {linesForSource.map((m) => (
                <option key={m.id} value={m.line_id}>
                  {m.line_id} ({m.rows}×{m.cols})
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>TARGET EDGE</span>
            <select
              className="mono"
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              disabled={busy}
            >
              <option value="">— choose —</option>
              {edges
                .filter((e) => e.id !== source)
                .map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.id} ({e.status})
                  </option>
                ))}
            </select>
          </label>
          <button
            type="button"
            className="btn btn--primary"
            disabled={busy || !source || !target || !lineId}
            onClick={() => void failover()}
          >
            Failover
          </button>
        </div>
        {msg ? (
          <div className="banner" style={{ margin: 8, background: "#1a3", color: "#fff" }}>
            <b>OK</b>&nbsp;{msg}
          </div>
        ) : null}
      </section>

      <section className="card">
        <header className="card__head">
          <h3 className="h3">All lines</h3>
        </header>
        <div className="card__body" style={{ padding: 0 }}>
          {lines.length === 0 ? (
            <div className="empty">No lines registered.</div>
          ) : (
            <table className="datagrid">
              <thead>
                <tr>
                  <th>Line</th>
                  <th>Tag</th>
                  <th>Assigned edge</th>
                  <th>Geometry</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {lines.map((l) => {
                  const m = meshes.find((mm) => mm.line_id === l.id);
                  return (
                    <tr key={l.id}>
                      <td className="id">{l.id}</td>
                      <td>{l.customer_tag}</td>
                      <td className="mono">{m?.edge_id ?? "—"}</td>
                      <td>
                        {l.rows}×{l.cols}
                      </td>
                      <td>
                        <span
                          className="led"
                          data-state={l.status === "live" ? "online" : "warn"}
                        >
                          <span className="led__dot" aria-hidden="true" />
                          {(l.status ?? "uncalibrated").toUpperCase()}
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
  );
}
