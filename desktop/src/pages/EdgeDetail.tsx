/**
 * Edge detail page.
 *
 * Live telemetry view for one Tactile Edge appliance. Snapshots the
 * REST resource on mount, then subscribes to the `/telemetry` SSE
 * stream to replace stale fields as new heartbeats arrive. If the SSE
 * channel drops we fall back to polling `/telemetry/recent` every 3s.
 */

import { useEffect, useRef, useState } from "react";
import { PageHeader } from "../components/PageHeader";
import { MeterBar } from "../components/MeterBar";
import { Spark } from "../components/Spark";
import { api } from "../lib/api";
import { subscribeEdgeTelemetry, type Subscription } from "../lib/sse";
import type { Edge, EdgeTelemetry } from "../lib/types";

const HISTORY_LEN = 120;
const POLL_FALLBACK_MS = 3_000;

export interface EdgeDetailProps {
  edgeId: string;
  onBack: () => void;
}

function fmtAge(iso: string | null): string {
  if (!iso) return "never";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "—";
  const s = Math.max(0, Math.floor((Date.now() - t) / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  return `${Math.floor(s / 3600)}h ago`;
}

export function EdgeDetail({ edgeId, onBack }: EdgeDetailProps): JSX.Element {
  const [edge, setEdge] = useState<Edge | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [sseLive, setSseLive] = useState(false);
  const [history, setHistory] = useState<{
    fps: number[];
    p99: number[];
    gpu: number[];
  }>({ fps: [], p99: [], gpu: [] });
  const subRef = useRef<Subscription | null>(null);

  useEffect(() => {
    let cancelled = false;
    setEdge(null);
    setErr(null);
    setHistory({ fps: [], p99: [], gpu: [] });

    void api
      .getEdge(edgeId)
      .then((row) => {
        if (cancelled) return;
        setEdge(row);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setErr(e instanceof Error ? e.message : String(e));
      });

    void api
      .recentEdgeTelemetry(edgeId)
      .then((rows) => {
        if (cancelled) return;
        setHistory({
          fps: rows.map((r) => r.frames_per_second),
          p99: rows.map((r) => r.inference_p99_ms),
          gpu: rows.map((r) => r.gpu_temp_c),
        });
      })
      .catch(() => {});

    const apply = (t: EdgeTelemetry): void => {
      setEdge((prev) => {
        if (!prev) return prev;
        return { ...prev, ...telemetryAsEdgeFields(t) };
      });
      setHistory((prev) => ({
        fps: appendBounded(prev.fps, t.frames_per_second, HISTORY_LEN),
        p99: appendBounded(prev.p99, t.inference_p99_ms, HISTORY_LEN),
        gpu: appendBounded(prev.gpu, t.gpu_temp_c, HISTORY_LEN),
      }));
    };

    void subscribeEdgeTelemetry(edgeId, apply, () => setSseLive(false)).then((s) => {
      if (cancelled) {
        s.close();
        return;
      }
      subRef.current = s;
      setSseLive(true);
    });

    // Belt-and-suspenders poller in case SSE never connects (e.g. backend
    // restart between mount and our subscribe call).
    const pollId = window.setInterval(() => {
      void api
        .recentEdgeTelemetry(edgeId)
        .then((rows) => {
          if (cancelled || rows.length === 0) return;
          const last = rows[rows.length - 1];
          if (last) apply(last);
        })
        .catch(() => {});
    }, POLL_FALLBACK_MS);

    return () => {
      cancelled = true;
      subRef.current?.close();
      subRef.current = null;
      window.clearInterval(pollId);
    };
  }, [edgeId]);

  if (err) {
    return (
      <div className="page">
        <PageHeader
          eyebrow={`EDGE · ${edgeId}`}
          title="Could not load edge"
          actions={
            <button type="button" className="btn" onClick={onBack}>
              ← Back
            </button>
          }
        />
        <div className="banner">
          <b>ERR</b>&nbsp;{err}
        </div>
      </div>
    );
  }

  if (!edge) {
    return (
      <div className="page">
        <PageHeader
          eyebrow={`EDGE · ${edgeId}`}
          title="Loading…"
          actions={
            <button type="button" className="btn" onClick={onBack}>
              ← Back
            </button>
          }
        />
      </div>
    );
  }

  const ramPct = edge.ram_total_mb > 0 ? (edge.ram_used_mb / edge.ram_total_mb) * 100 : 0;

  return (
    <div className="page">
      <PageHeader
        eyebrow={`EDGE · ${edge.id}`}
        title={edge.hostname || edge.id}
        actions={
          <>
            <span className="led" data-state={edge.status}>
              <span className="led__dot" aria-hidden="true" />
              {edge.status.toUpperCase()}
            </span>
            <button type="button" className="btn" onClick={onBack}>
              ← Back
            </button>
          </>
        }
      />

      {!sseLive ? (
        <div className="banner banner--warn">
          <b>POLLING.</b>&nbsp;Telemetry SSE channel is not live; falling
          back to {POLL_FALLBACK_MS / 1000}s replay polling.
        </div>
      ) : null}

      <div className="grid grid--detail">
        <section className="card">
          <header className="card__head">
            <h3 className="h3">Compute</h3>
            <span className="mono" style={{ fontSize: 11, color: "var(--muted)" }}>
              last seen {fmtAge(edge.last_seen_at)}
            </span>
          </header>
          <div className="card__body">
            <MeterBar label="CPU" value={edge.cpu_pct} max={100} warnAt={70} dangerAt={90} unit="%" />
            <MeterBar label="GPU" value={edge.gpu_pct} max={100} warnAt={70} dangerAt={90} unit="%" />
            <MeterBar
              label="GPU TEMP"
              value={edge.gpu_temp_c}
              max={100}
              warnAt={70}
              dangerAt={85}
              unit="°C"
            />
            <MeterBar
              label="CPU TEMP"
              value={edge.cpu_temp_c}
              max={100}
              warnAt={70}
              dangerAt={85}
              unit="°C"
            />
            <MeterBar
              label="RAM"
              value={ramPct}
              max={100}
              warnAt={75}
              dangerAt={90}
              unit="%"
              digits={1}
            />
            <MeterBar
              label="POWER"
              value={edge.power_mw / 1000}
              max={15}
              warnAt={70}
              dangerAt={90}
              unit="W"
              digits={2}
            />
          </div>
        </section>

        <section className="card">
          <header className="card__head">
            <h3 className="h3">Inference</h3>
            <span className="mono" style={{ fontSize: 11, color: "var(--muted)" }}>
              agent {edge.agent_version || "—"}
            </span>
          </header>
          <div className="card__body">
            <dl className="kv">
              <div>
                <dt>Model</dt>
                <dd>{edge.model}</dd>
              </div>
              <div>
                <dt>Serial</dt>
                <dd>{edge.serial || "—"}</dd>
              </div>
              <div>
                <dt>Firmware</dt>
                <dd>{edge.firmware_version || "—"}</dd>
              </div>
              <div>
                <dt>Site</dt>
                <dd>{edge.site || "—"}</dd>
              </div>
              <div>
                <dt>p50 latency</dt>
                <dd>{edge.inference_p50_ms.toFixed(2)} ms</dd>
              </div>
              <div>
                <dt>p99 latency</dt>
                <dd>{edge.inference_p99_ms.toFixed(2)} ms</dd>
              </div>
              <div>
                <dt>Frame rate</dt>
                <dd>{edge.frames_per_second.toFixed(1)} fps</dd>
              </div>
              <div>
                <dt>Enrolled</dt>
                <dd>{edge.enrolled_at.slice(0, 19).replace("T", " ")}</dd>
              </div>
            </dl>
          </div>
        </section>
      </div>

      <section className="card">
        <header className="card__head">
          <h3 className="h3">FPS (last 120 samples)</h3>
          <span className="mono" style={{ fontSize: 11, color: "var(--muted)" }}>
            {history.fps.length} pts
          </span>
        </header>
        <div className="card__body">
          <Spark values={history.fps} />
        </div>
      </section>

      <section className="card">
        <header className="card__head">
          <h3 className="h3">p99 latency (ms)</h3>
          <span className="mono" style={{ fontSize: 11, color: "var(--muted)" }}>
            {history.p99.length} pts
          </span>
        </header>
        <div className="card__body">
          <Spark values={history.p99} threshold={50} />
        </div>
      </section>

      <section className="card">
        <header className="card__head">
          <h3 className="h3">GPU temperature (°C)</h3>
          <span className="mono" style={{ fontSize: 11, color: "var(--muted)" }}>
            {history.gpu.length} pts
          </span>
        </header>
        <div className="card__body">
          <Spark values={history.gpu} threshold={80} />
        </div>
      </section>
    </div>
  );
}

function telemetryAsEdgeFields(t: EdgeTelemetry): Partial<Edge> {
  return {
    status: t.status,
    last_seen_at: t.ts,
    cpu_pct: t.cpu_pct,
    gpu_pct: t.gpu_pct,
    gpu_temp_c: t.gpu_temp_c,
    cpu_temp_c: t.cpu_temp_c,
    ram_used_mb: t.ram_used_mb,
    ram_total_mb: t.ram_total_mb,
    power_mw: t.power_mw,
    inference_p50_ms: t.inference_p50_ms,
    inference_p99_ms: t.inference_p99_ms,
    frames_per_second: t.frames_per_second,
    firmware_version: t.firmware_version,
    agent_version: t.agent_version,
  };
}

function appendBounded(arr: number[], next: number, max: number): number[] {
  const out = arr.concat(next);
  if (out.length > max) out.splice(0, out.length - max);
  return out;
}
