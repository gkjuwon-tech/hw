/**
 * Status bar — the bottom HMI strip.
 *
 * Renders persistent process state: the API connection LED, the
 * currently selected edge box's status + headline metrics, and a
 * wall-clock readout. Every figure here is monospaced + tabular so it
 * never reflows the layout when a digit changes.
 */

import type { Edge, EdgeStatus } from "../lib/types";

export interface StatusBarProps {
  apiStatus: "ok" | "boot" | "down";
  edge: Edge | null;
  edgeStatus: EdgeStatus | "boot";
  now: Date;
}

function fmtNum(n: number | undefined, digits = 1): string {
  if (n === undefined || n === null || Number.isNaN(n)) return "—";
  return n.toFixed(digits);
}

function fmtClock(d: Date): string {
  const hh = d.getHours().toString().padStart(2, "0");
  const mm = d.getMinutes().toString().padStart(2, "0");
  const ss = d.getSeconds().toString().padStart(2, "0");
  return `${hh}:${mm}:${ss}`;
}

export function StatusBar({
  apiStatus,
  edge,
  edgeStatus,
  now,
}: StatusBarProps): JSX.Element {
  return (
    <footer className="statusbar" role="contentinfo">
      <div className="statusbar__pair">
        <span className="led" data-state={apiStatus === "ok" ? "online" : apiStatus}>
          <span className="led__dot" aria-hidden="true" />
          API&nbsp;{apiStatus === "ok" ? "CONNECTED" : apiStatus === "down" ? "DOWN" : "BOOT"}
        </span>
      </div>
      <div className="statusbar__pair">
        <span className="led" data-state={edgeStatus}>
          <span className="led__dot" aria-hidden="true" />
          EDGE&nbsp;{edgeStatus.toUpperCase()}
        </span>
      </div>
      <div className="statusbar__pair">
        <label>FPS</label>
        <span>{fmtNum(edge?.frames_per_second, 1)}</span>
      </div>
      <div className="statusbar__pair">
        <label>P50 / P99</label>
        <span>
          {fmtNum(edge?.inference_p50_ms, 1)}/{fmtNum(edge?.inference_p99_ms, 1)}&nbsp;ms
        </span>
      </div>
      <div className="statusbar__pair">
        <label>GPU</label>
        <span>{fmtNum(edge?.gpu_temp_c, 1)}&nbsp;°C</span>
      </div>
      <div className="statusbar__pair">
        <label>PWR</label>
        <span>{((edge?.power_mw ?? 0) / 1000).toFixed(2)}&nbsp;W</span>
      </div>
      <div className="statusbar__pair">
        <label>CLOCK</label>
        <span>{fmtClock(now)}</span>
      </div>
    </footer>
  );
}
