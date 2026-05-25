/**
 * Tactile Cloud HTTP client.
 *
 * The base URL is resolved once at app startup via the Electron IPC bridge
 * (`window.conet.getApiBase()`). On the dev fallback path where the bridge
 * is unavailable (e.g. running `vite dev` without Electron), we point at
 * the canonical local backend on :8000 instead, so the React app stays
 * usable during pure-frontend iteration.
 *
 * Authentication: when a bearer token is present in localStorage under
 * `conet.api_key`, it is attached as `Authorization: Bearer ...`. The
 * Settings page is the one place that writes that key.
 */

import type {
  ApiError,
  Claim,
  ClaimCreated,
  Edge,
  EdgeTelemetry,
  HealthResponse,
  InspectionEvent,
  Line,
  MeshSegment,
  MeshTopology,
  Recipe,
  RecipePatch,
  TeachCaptureResult,
  TeachFinishResult,
  TeachStatus,
} from "./types";

let cachedBase: string | null | undefined = undefined;

export const FALLBACK_BASE = "http://127.0.0.1:8000";
const TOKEN_KEY = "conet.api_key";

async function resolveBase(): Promise<string> {
  if (cachedBase !== undefined) {
    return cachedBase ?? FALLBACK_BASE;
  }
  if (typeof window !== "undefined" && window.conet?.getApiBase) {
    try {
      cachedBase = await window.conet.getApiBase();
    } catch {
      cachedBase = null;
    }
  } else {
    cachedBase = null;
  }
  return cachedBase ?? FALLBACK_BASE;
}

function getStoredToken(): string {
  if (typeof window === "undefined") return "";
  try {
    return window.localStorage.getItem(TOKEN_KEY) ?? "";
  } catch {
    return "";
  }
}

export function setApiToken(token: string): void {
  if (typeof window === "undefined") return;
  try {
    if (token) {
      window.localStorage.setItem(TOKEN_KEY, token);
    } else {
      window.localStorage.removeItem(TOKEN_KEY);
    }
  } catch {
    // ignore storage denial in private mode
  }
}

export function getApiToken(): string {
  return getStoredToken();
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const base = await resolveBase();
  const token = getStoredToken();
  const res = await fetch(`${base}${path}`, {
    ...init,
    headers: {
      accept: "application/json",
      "content-type": "application/json",
      ...(token ? { authorization: `Bearer ${token}` } : {}),
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    const err = new Error(
      `${res.status} ${res.statusText}: ${text.slice(0, 200)}`,
    ) as ApiError;
    err.status = res.status;
    err.body = text;
    throw err;
  }
  if (res.status === 204) return undefined as unknown as T;
  return (await res.json()) as T;
}

export const api = {
  async health(): Promise<HealthResponse> {
    return request<HealthResponse>("/healthz");
  },

  // ── lines ─────────────────────────────────────────────────────────
  async listLines(): Promise<Line[]> {
    return request<Line[]>("/v1/lines");
  },
  async getLine(lineId: string): Promise<Line> {
    return request<Line>(`/v1/lines/${encodeURIComponent(lineId)}`);
  },
  async recentEvents(lineId: string): Promise<InspectionEvent[]> {
    return request<InspectionEvent[]>(
      `/v1/lines/${encodeURIComponent(lineId)}/events/recent`,
    );
  },

  // ── edges (Jetson appliances) ─────────────────────────────────────
  async listEdges(): Promise<Edge[]> {
    return request<Edge[]>("/v1/edges");
  },
  async getEdge(edgeId: string): Promise<Edge> {
    return request<Edge>(`/v1/edges/${encodeURIComponent(edgeId)}`);
  },
  async enrollEdge(payload: {
    id: string;
    hostname: string;
    serial?: string;
    model?: string;
    site?: string;
  }): Promise<Edge> {
    return request<Edge>("/v1/edges", {
      method: "POST",
      body: JSON.stringify({
        serial: "",
        model: "jetson-orin-nano-8gb",
        site: "",
        ...payload,
      }),
    });
  },
  async recentEdgeTelemetry(edgeId: string): Promise<EdgeTelemetry[]> {
    return request<EdgeTelemetry[]>(
      `/v1/edges/${encodeURIComponent(edgeId)}/telemetry/recent`,
    );
  },

  // ── mesh segments (installed roll-mesh pieces) ────────────────────
  async listMeshes(opts?: { lineId?: string; edgeId?: string }): Promise<MeshSegment[]> {
    const params = new URLSearchParams();
    if (opts?.lineId) params.set("line_id", opts.lineId);
    if (opts?.edgeId) params.set("edge_id", opts.edgeId);
    const qs = params.toString();
    return request<MeshSegment[]>(`/v1/meshes${qs ? `?${qs}` : ""}`);
  },
  async installMesh(payload: {
    id: string;
    line_id: string;
    edge_id?: string | null;
    roll_lot: string;
    belt_width_mm?: number;
    length_mm?: number;
    rows: number;
    cols: number;
    expected_lifetime_days?: number;
    notes?: string;
  }): Promise<MeshSegment> {
    return request<MeshSegment>("/v1/meshes", {
      method: "POST",
      body: JSON.stringify({
        belt_width_mm: 0,
        length_mm: 0,
        expected_lifetime_days: 180,
        notes: "",
        ...payload,
      }),
    });
  },

  // ── lines (create line) ─────────────────────────────────────────────
  async createLine(payload: {
    id: string;
    customer_tag?: string;
    rows: number;
    cols: number;
  }): Promise<Line> {
    return request<Line>("/v1/lines", {
      method: "POST",
      body: JSON.stringify({ customer_tag: "", ...payload }),
    });
  },

  async updateLine(
    lineId: string,
    payload: { customer_tag?: string; threshold_score?: number; threshold_hits?: number },
  ): Promise<Line> {
    return request<Line>(`/v1/lines/${encodeURIComponent(lineId)}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  },

  // ── claims / enrollment ─────────────────────────────────────────────
  async listClaims(): Promise<Claim[]> {
    return request<Claim[]>("/v1/claims");
  },
  async createClaim(payload: {
    label?: string;
    site?: string;
    expected_serial?: string;
    expected_model?: string;
    ttl_hours?: number;
  }): Promise<ClaimCreated> {
    return request<ClaimCreated>("/v1/claims", {
      method: "POST",
      body: JSON.stringify({
        label: "",
        site: "",
        expected_serial: "",
        expected_model: "jetson-orin-nano-8gb",
        ttl_hours: 24,
        ...payload,
      }),
    });
  },
  async revokeClaim(claimId: string): Promise<void> {
    return request<void>(`/v1/claims/${encodeURIComponent(claimId)}/revoke`, {
      method: "POST",
    });
  },
  async redeemClaim(payload: {
    token: string;
    edge_id: string;
    hostname?: string;
    serial: string;
    model?: string;
    firmware_version: string;
  }): Promise<Edge> {
    return request<Edge>("/v1/claims/redeem", {
      method: "POST",
      body: JSON.stringify({
        hostname: "",
        model: "jetson-orin-nano-8gb",
        ...payload,
      }),
    });
  },

  // ── teach (5-sample wizard) ─────────────────────────────────────────
  async teachStatus(edgeId: string): Promise<TeachStatus> {
    return request<TeachStatus>(`/v1/edges/${encodeURIComponent(edgeId)}/teach/status`);
  },
  async teachStart(edgeId: string, lineId: string): Promise<TeachStatus> {
    return request<TeachStatus>(`/v1/edges/${encodeURIComponent(edgeId)}/teach/start`, {
      method: "POST",
      body: JSON.stringify({ line_id: lineId }),
    });
  },
  async teachCapture(edgeId: string, data: number[]): Promise<TeachCaptureResult> {
    return request<TeachCaptureResult>(
      `/v1/edges/${encodeURIComponent(edgeId)}/teach/capture`,
      {
        method: "POST",
        body: JSON.stringify({ data }),
      },
    );
  },
  async teachFinish(edgeId: string): Promise<TeachFinishResult> {
    return request<TeachFinishResult>(
      `/v1/edges/${encodeURIComponent(edgeId)}/teach/finish`,
      { method: "POST" },
    );
  },
  async teachAbort(edgeId: string): Promise<void> {
    return request<void>(`/v1/edges/${encodeURIComponent(edgeId)}/teach`, {
      method: "DELETE",
    });
  },

  // ── mesh fabric topology ────────────────────────────────────────────
  async meshTopology(): Promise<MeshTopology> {
    return request<MeshTopology>("/v1/mesh/topology");
  },
  async meshFailover(payload: {
    source_edge_id: string;
    target_edge_id: string;
    line_id: string;
  }): Promise<{ status: string; line_id: string; new_edge_id: string; old_edge_id: string }> {
    return request("/v1/mesh/failover", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  // ── recipes (per-product configs) ───────────────────────────────────
  async listRecipes(lineId?: string): Promise<Recipe[]> {
    const qs = lineId ? `?line_id=${encodeURIComponent(lineId)}` : "";
    return request<Recipe[]>(`/v1/recipes${qs}`);
  },
  async getRecipe(recipeId: string): Promise<Recipe> {
    return request<Recipe>(`/v1/recipes/${encodeURIComponent(recipeId)}`);
  },
  async createRecipe(payload: RecipePatch & { name: string }): Promise<Recipe> {
    return request<Recipe>("/v1/recipes", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
  async updateRecipe(recipeId: string, payload: RecipePatch): Promise<Recipe> {
    return request<Recipe>(`/v1/recipes/${encodeURIComponent(recipeId)}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  },
  async deleteRecipe(recipeId: string): Promise<void> {
    return request<void>(`/v1/recipes/${encodeURIComponent(recipeId)}`, {
      method: "DELETE",
    });
  },
  async loadRecipe(lineId: string, recipeId: string): Promise<{
    line_id: string;
    recipe_id: string;
    recipe_name: string;
    threshold_score: number;
    threshold_hits: number;
  }> {
    return request(`/v1/lines/${encodeURIComponent(lineId)}/load_recipe`, {
      method: "POST",
      body: JSON.stringify({ recipe_id: recipeId }),
    });
  },
};

export async function apiBaseUrl(): Promise<string> {
  return resolveBase();
}

export function resetBaseCache(): void {
  cachedBase = undefined;
}
