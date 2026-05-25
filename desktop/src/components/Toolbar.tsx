/**
 * Toolbar — top-of-content button strip (industrial HMI pattern).
 *
 * Hosts the route nav (one button per page) on the left and a
 * crumb-style label on the right. The currently selected route gets
 * `aria-pressed="true"`, which the CSS bevels inward.
 */

import type { ReactNode } from "react";
import type { Route } from "../App";

export interface ToolbarProps {
  current: Route;
  onNavigate: (r: Route) => void;
  crumb: ReactNode;
}

const NAV: ReadonlyArray<{ id: Route; label: string }> = [
  { id: "overview", label: "Overview" },
  { id: "edges", label: "Edges" },
  { id: "claims", label: "Claims" },
  { id: "lines", label: "Lines" },
  { id: "mesh", label: "Mesh" },
  { id: "fabric", label: "Fabric" },
  { id: "recipes", label: "Recipes" },
  { id: "calibrate", label: "Teach" },
  { id: "settings", label: "Settings" },
  { id: "about", label: "About" },
];

export function Toolbar({ current, onNavigate, crumb }: ToolbarProps): JSX.Element {
  return (
    <div className="toolbar" role="toolbar" aria-label="Primary">
      <div className="toolbar-group">
        {NAV.map((item) => {
          const active =
            current === item.id ||
            (current === "line-detail" && item.id === "lines") ||
            (current === "line-tune" && item.id === "lines") ||
            (current === "edge-detail" && item.id === "edges");
          return (
            <button
              key={item.id}
              type="button"
              className="btn"
              aria-pressed={active ? true : undefined}
              onClick={() => onNavigate(item.id)}
            >
              {item.label}
            </button>
          );
        })}
      </div>
      <div className="toolbar__crumb">{crumb}</div>
    </div>
  );
}
