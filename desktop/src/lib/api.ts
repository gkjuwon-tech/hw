/**
 * Tiny fetch wrapper around the FastAPI sidecar.
 *
 * The base URL is resolved once at app startup via the Electron IPC bridge
 * (`window.conet.getApiBase()`). On the dev fallback path where the bridge
 * is unavailable (e.g. running `vite dev` without Electron), we point at
 * the canonical local backend on :8000 instead, so the React app stays
 * usable during pure-frontend iteration.
 */

import type { HealthResponse, InspectionEvent, Line } from "./types";

let cachedBase: string | null | undefined = undefined;

async function resolveBase(): Promise<string> {
  if (cachedBase !== undefined) {
    return cachedBase ?? "http://127.0.0.1:8000";
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
  return cachedBase ?? "http://127.0.0.1:8000";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const base = await resolveBase();
  const res = await fetch(`${base}${path}`, {
    ...init,
    headers: {
      accept: "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}: ${text.slice(0, 200)}`);
  }
  return (await res.json()) as T;
}

export const api = {
  async health(): Promise<HealthResponse> {
    return request<HealthResponse>("/healthz");
  },

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
};

export async function apiBaseUrl(): Promise<string> {
  return resolveBase();
}
