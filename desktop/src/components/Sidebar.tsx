import type { Route } from "../App";

export interface SidebarProps {
  current: Route;
  onNavigate: (r: Route) => void;
  lineCount: number;
  apiStatus: "ok" | "boot" | "down";
  buildLabel: string;
}

const NAV: ReadonlyArray<{ id: Route; label: string }> = [
  { id: "lines", label: "Lines" },
  { id: "calibrate", label: "Calibrate" },
  { id: "settings", label: "Settings" },
  { id: "about", label: "About" },
];

export function Sidebar({
  current,
  onNavigate,
  lineCount,
  apiStatus,
  buildLabel,
}: SidebarProps): JSX.Element {
  return (
    <aside className="sidebar">
      <div className="sidebar__brand">
        <span className="sidebar__mark" aria-hidden="true" />
        <span className="sidebar__word">Conet&nbsp;Tactile</span>
      </div>

      <nav className="sidebar__nav" aria-label="Primary">
        {NAV.map((item) => (
          <button
            key={item.id}
            type="button"
            aria-current={current === item.id ? "page" : undefined}
            onClick={() => onNavigate(item.id)}
          >
            <span>{item.label}</span>
            {item.id === "lines" ? (
              <span className="count mono">{lineCount}</span>
            ) : null}
          </button>
        ))}
      </nav>

      <div className="sidebar__foot">
        <span className="status" data-state={apiStatus}>
          <span className="dot" aria-hidden="true" />
          {apiStatus === "ok"
            ? "Sidecar live"
            : apiStatus === "boot"
              ? "Booting"
              : "Sidecar down"}
        </span>
        <span className="build">{buildLabel}</span>
      </div>
    </aside>
  );
}
