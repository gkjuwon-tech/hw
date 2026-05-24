/**
 * Wire types for the FastAPI sidecar.
 *
 * The desktop is now a real client of the production control plane —
 * lines + edges + mesh segments are all first-class resources. We model
 * the subset of fields the operator UI surfaces; the backend's full
 * schemas live in `backend/app/schemas.py`.
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

export type EdgeStatus = "online" | "degraded" | "offline";

export interface Edge {
  id: string;
  org_id: string;
  hostname: string;
  serial: string;
  model: string;
  site: string;
  firmware_version: string;
  agent_version: string;
  status: EdgeStatus;
  last_seen_at: string | null;
  enrolled_at: string;
  cpu_pct: number;
  gpu_pct: number;
  gpu_temp_c: number;
  cpu_temp_c: number;
  ram_used_mb: number;
  ram_total_mb: number;
  power_mw: number;
  inference_p50_ms: number;
  inference_p99_ms: number;
  frames_per_second: number;
}

export interface EdgeTelemetry {
  edge_id: string;
  status: EdgeStatus;
  ts: string | null;
  cpu_pct: number;
  gpu_pct: number;
  gpu_temp_c: number;
  cpu_temp_c: number;
  ram_used_mb: number;
  ram_total_mb: number;
  power_mw: number;
  inference_p50_ms: number;
  inference_p99_ms: number;
  frames_per_second: number;
  firmware_version: string;
  agent_version: string;
}

export interface MeshSegment {
  id: string;
  org_id: string;
  line_id: string;
  edge_id: string | null;
  roll_lot: string;
  belt_width_mm: number;
  length_mm: number;
  rows: number;
  cols: number;
  installed_at: string;
  expected_lifetime_days: number;
  health_pct: number;
  dead_cells: number;
  notes: string;
}

export interface ApiError extends Error {
  status: number;
  body: string;
}
