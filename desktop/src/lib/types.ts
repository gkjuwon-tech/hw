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
  threshold_score?: number;
  threshold_hits?: number;
  drift?: number;
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

// ── claim/redeem flow ───────────────────────────────────────────────

export interface ClaimCreated {
  id: string;
  token: string;
  label: string;
  site: string;
  expires_at: string;
}

export interface Claim {
  id: string;
  label: string;
  site: string;
  expected_serial: string;
  expected_model: string;
  expires_at: string;
  created_at: string;
  redeemed_at: string | null;
  redeemed_edge_id: string | null;
  revoked: boolean;
}

// ── teach session ───────────────────────────────────────────────────

export interface TeachStatus {
  edge_id: string;
  line_id: string | null;
  captured: number;
  required: number;
  remaining: number;
  status: "idle" | "in_progress" | "ready" | "completed" | "failed";
  elapsed_s: number;
}

export interface TeachCaptureResult {
  edge_id: string;
  line_id: string;
  captured: number;
  remaining: number;
  status: string;
  message: string;
}

export interface TeachFinishResult {
  edge_id: string;
  line_id: string;
  n_samples: number;
  rows: number;
  cols: number;
  mean_min: number;
  mean_max: number;
  line_status: string;
  message: string;
}

// ── mesh fabric ─────────────────────────────────────────────────────

export interface MeshPeer {
  edge_id: string;
  ip: string;
  port: number;
  alive: boolean;
  capacity_free_pct: number;
  last_announce_ago_s: number;
  latency_ms: Record<string, number>;
}

export interface MeshTopology {
  nodes: MeshPeer[];
  edges_count: number;
  alive_count: number;
}

// ── recipes (per-product saved configs) ─────────────────────────────

export type TriggerMode = "continuous" | "external" | "software" | "encoder";

export interface Recipe {
  id: string;
  org_id: string;
  line_id: string | null;
  name: string;
  product_sku: string;
  description: string;
  threshold_score: number;
  threshold_hits: number;
  sigma_threshold: number;
  drift_alert_z: number;
  roi_x0: number;
  roi_y0: number;
  roi_x1: number;
  roi_y1: number;
  gain: number;
  gamma: number;
  sharpen: number;
  denoise: number;
  blob_min_area: number;
  blob_max_area: number;
  rotation_tolerance_deg: number;
  scale_tolerance_pct: number;
  trigger_mode: TriggerMode;
  debounce_ms: number;
  reject_queue_depth: number;
  strobe_duty_pct: number;
  strobe_delay_us: number;
  logic_dsl: string;
  created_at: string;
  updated_at: string;
}

export type RecipePatch = Partial<Omit<Recipe, "id" | "org_id" | "created_at" | "updated_at">>;

