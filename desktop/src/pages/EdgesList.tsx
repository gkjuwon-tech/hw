/**
 * Edges list page.
 *
 * Dense, sortable-ish (by status implicitly) inventory of every
 * enrolled Tactile Edge appliance, plus a primitive enroll-by-id
 * form that POSTs to /v1/edges.
 */

import { useState } from "react";
import { PageHeader } from "../components/PageHeader";
import { api } from "../lib/api";
import type { ApiError, Edge } from "../lib/types";

export interface EdgesListProps {
  edges: Edge[];
  onOpen: (edgeId: string) => void;
  onRefresh: () => Promise<void>;
  onGoToClaims?: () => void;
}

function fmtAge(iso: string | null): string {
  if (!iso) return "never";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "—";
  const s = Math.max(0, Math.floor((Date.now() - t) / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86_400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86_400)}d ago`;
}

export function EdgesList({
  edges,
  onOpen,
  onRefresh,
  onGoToClaims,
}: EdgesListProps): JSX.Element {
  const [id, setId] = useState("");
  const [hostname, setHostname] = useState("");
  const [site, setSite] = useState("");
  const [serial, setSerial] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const enroll = async (): Promise<void> => {
    if (!id.trim()) {
      setErr("edge id is required");
      return;
    }
    if (serial.trim().length < 4) {
      setErr("serial must be at least 4 chars (claim-redeem recommended)");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      await api.enrollEdge({
        id: id.trim(),
        hostname: hostname.trim() || id.trim(),
        serial: serial.trim(),
        site: site.trim(),
      });
      setId("");
      setHostname("");
      setSite("");
      setSerial("");
      await onRefresh();
    } catch (e) {
      const apiErr = e as ApiError;
      setErr(apiErr.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page">
      <PageHeader
        eyebrow="EDGES"
        title="Tactile Edge fleet"
        lede="Every Jetson appliance enrolled to this org. Click a row to drill into live telemetry."
        actions={
          <button
            type="button"
            className="btn"
            onClick={() => void onRefresh()}
          >
            Refresh
          </button>
        }
      />

      <section className="card">
        <header className="card__head">
          <h3 className="h3">Enroll edge — legacy direct path</h3>
          <span className="mono" style={{ fontSize: 11, color: "var(--muted)" }}>
            POST /v1/edges · prefer claim-redeem
          </span>
        </header>
        <div
          className="card__body"
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr 1fr 1fr auto",
            gap: 8,
            alignItems: "end",
          }}
        >
          <label className="field">
            <span>EDGE ID</span>
            <input
              type="text"
              value={id}
              onChange={(e) => setId(e.target.value)}
              placeholder="edge-floor3-line7"
              disabled={busy}
            />
          </label>
          <label className="field">
            <span>SERIAL *</span>
            <input
              type="text"
              value={serial}
              onChange={(e) => setSerial(e.target.value)}
              placeholder="hardware PCB serial"
              disabled={busy}
            />
          </label>
          <label className="field">
            <span>HOSTNAME</span>
            <input
              type="text"
              value={hostname}
              onChange={(e) => setHostname(e.target.value)}
              placeholder="(default: same as id)"
              disabled={busy}
            />
          </label>
          <label className="field">
            <span>SITE</span>
            <input
              type="text"
              value={site}
              onChange={(e) => setSite(e.target.value)}
              placeholder="plant-3"
              disabled={busy}
            />
          </label>
          <button
            type="button"
            className="btn btn--primary"
            onClick={() => void enroll()}
            disabled={busy}
          >
            Enroll
          </button>
        </div>
        <div className="card__body" style={{ paddingTop: 0 }}>
          <p className="lede" style={{ fontSize: 12 }}>
            Legacy path. The production flow uses a one-time claim token
            redeemed by the Edge appliance with its hardware serial and
            firmware version.
            {onGoToClaims ? (
              <>
                {" "}
                <button
                  type="button"
                  className="btn btn--ghost"
                  onClick={() => onGoToClaims()}
                >
                  Open Claims
                </button>
              </>
            ) : null}
          </p>
        </div>
        {err ? (
          <div className="banner" style={{ margin: 8 }}>
            <b>ERR</b>&nbsp;{err}
          </div>
        ) : null}
      </section>

      <section className="card">
        <header className="card__head">
          <h3 className="h3">Inventory</h3>
          <span className="mono" style={{ fontSize: 11, color: "var(--muted)" }}>
            {edges.length} total
          </span>
        </header>
        <div className="card__body" style={{ padding: 0 }}>
          {edges.length === 0 ? (
            <div className="empty">No edges enrolled yet.</div>
          ) : (
            <table className="datagrid">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Hostname</th>
                  <th>Status</th>
                  <th>Site</th>
                  <th className="right">CPU %</th>
                  <th className="right">GPU %</th>
                  <th className="right">GPU °C</th>
                  <th className="right">FPS</th>
                  <th className="right">p99 ms</th>
                  <th className="right">Power</th>
                  <th>Last seen</th>
                </tr>
              </thead>
              <tbody>
                {edges.map((e) => (
                  <tr
                    key={e.id}
                    className="is-clickable"
                    onClick={() => onOpen(e.id)}
                  >
                    <td className="id">{e.id}</td>
                    <td>{e.hostname || "—"}</td>
                    <td>
                      <span className="led" data-state={e.status}>
                        <span className="led__dot" aria-hidden="true" />
                        {e.status.toUpperCase()}
                      </span>
                    </td>
                    <td>{e.site || "—"}</td>
                    <td className="right">{e.cpu_pct.toFixed(1)}</td>
                    <td className="right">{e.gpu_pct.toFixed(1)}</td>
                    <td className="right">{e.gpu_temp_c.toFixed(1)}</td>
                    <td className="right">{e.frames_per_second.toFixed(1)}</td>
                    <td className="right">{e.inference_p99_ms.toFixed(1)}</td>
                    <td className="right">{(e.power_mw / 1000).toFixed(2)} W</td>
                    <td>{fmtAge(e.last_seen_at)}</td>
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
