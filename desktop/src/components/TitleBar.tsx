/**
 * Title bar — the lime strip across the very top of the window.
 *
 * Carries the product mark, the resolved sidecar host, and the agent
 * build label. Acts as an Electron drag region (everything but the
 * meta strip is `-webkit-app-region: drag`).
 */

import type { EdgeStatus } from "../lib/types";

export interface TitleBarProps {
  hostname: string;
  buildLabel: string;
  edgeStatus: EdgeStatus | "boot";
}

const STATUS_LABEL: Record<TitleBarProps["edgeStatus"], string> = {
  online: "ONLINE",
  degraded: "DEGRADED",
  offline: "OFFLINE",
  boot: "BOOTING",
};

export function TitleBar({
  hostname,
  buildLabel,
  edgeStatus,
}: TitleBarProps): JSX.Element {
  return (
    <header className="titlebar" role="banner">
      <div className="titlebar__brand">
        <span className="titlebar__mark" aria-hidden="true" />
        CONET&nbsp;TACTILE&nbsp;— OPERATOR
      </div>
      <div className="titlebar__meta">
        <span>
          HOST <b>{hostname || "—"}</b>
        </span>
        <span>
          EDGE <b>{STATUS_LABEL[edgeStatus]}</b>
        </span>
        <span>
          BUILD <b>{buildLabel}</b>
        </span>
      </div>
      <div className="titlebar__chrome" aria-hidden="true">
        {/* Decorative window dots — Electron OS chrome lives above this. */}
        <span style={{ color: "rgba(255,255,255,0.6)", fontSize: 10 }}>
          _ &nbsp; □ &nbsp; ×
        </span>
      </div>
    </header>
  );
}
