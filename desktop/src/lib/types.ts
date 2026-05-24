/**
 * Wire types for the FastAPI sidecar. We model only the fields the desktop
 * surface actually renders — the backend's full schemas live in
 * `backend/app/schemas.py`. If a field appears here, the desktop displays it;
 * if a field is in the backend but not here, the desktop deliberately
 * ignores it.
 */

export interface ConetBridge {
  getApiBase: () => Promise<string | null>;
  openExternal: (url: string) => Promise<void>;
  platform: NodeJS.Platform;
}

declare global {
  interface Window {
    conet?: ConetBridge;
  }
}

export type LineStatus = "live" | "uncalibrated" | "error" | "idle";

export interface Line {
  id: string;
  customer_tag: string;
  rows: number;
  cols: number;
  created_at: string;
  status?: LineStatus;
  recent_score?: number | null;
  drift_z?: number | null;
}

export interface InspectionEvent {
  ts: string;
  line_id: string;
  score: number;
  passed: boolean;
  drift_z?: number | null;
  heatmap?: number[][] | null;
}

export interface HealthResponse {
  status: "ok";
  service: string;
  version: string;
  environment: string;
}
