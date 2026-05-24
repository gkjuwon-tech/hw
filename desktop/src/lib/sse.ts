/**
 * SSE subscribers — inspection events (per line) AND edge telemetry
 * (per edge box).
 *
 * Both use the same loop shape: open `text/event-stream`, parse JSON
 * frames from `onmessage`, retry with capped exponential backoff on
 * disconnect. The two functions are kept as separate exports so each
 * has its own typed callback contract.
 */

import type { EdgeTelemetry, InspectionEvent } from "./types";
import { apiBaseUrl, getApiToken } from "./api";

export interface Subscription {
  close: () => void;
}

interface SubscribeOptions<T> {
  url: string;
  onData: (item: T) => void;
  onError?: (err: Error) => void;
}

async function subscribe<T>(opts: SubscribeOptions<T>): Promise<Subscription> {
  const { url, onData, onError } = opts;
  let es: EventSource | null = null;
  let closed = false;
  let backoffMs = 500;
  // The native EventSource does not allow setting Authorization headers.
  // We append the token as a query param the backend accepts (also
  // honored by the existing /v1/lines/.../events route). If no token is
  // configured we simply skip the query string.
  const token = getApiToken();
  const sep = url.includes("?") ? "&" : "?";
  const finalUrl = token ? `${url}${sep}access_token=${encodeURIComponent(token)}` : url;

  const connect = (): void => {
    if (closed) return;
    es = new EventSource(finalUrl);
    es.onopen = () => {
      backoffMs = 500;
    };
    es.onmessage = (msg) => {
      try {
        const data = JSON.parse(msg.data) as T;
        onData(data);
      } catch {
        // ignore non-JSON keepalive frames
      }
    };
    es.onerror = () => {
      es?.close();
      es = null;
      if (closed) return;
      onError?.(new Error(`SSE dropped, retrying in ${backoffMs}ms`));
      window.setTimeout(connect, backoffMs);
      backoffMs = Math.min(backoffMs * 2, 8_000);
    };
  };

  connect();
  return {
    close: () => {
      closed = true;
      es?.close();
      es = null;
    },
  };
}

export async function subscribeLineEvents(
  lineId: string,
  onEvent: (e: InspectionEvent) => void,
  onError?: (err: Error) => void,
): Promise<Subscription> {
  const base = await apiBaseUrl();
  return subscribe<InspectionEvent>({
    url: `${base}/v1/lines/${encodeURIComponent(lineId)}/events`,
    onData: onEvent,
    onError,
  });
}

export async function subscribeEdgeTelemetry(
  edgeId: string,
  onSnapshot: (t: EdgeTelemetry) => void,
  onError?: (err: Error) => void,
): Promise<Subscription> {
  const base = await apiBaseUrl();
  return subscribe<EdgeTelemetry>({
    url: `${base}/v1/edges/${encodeURIComponent(edgeId)}/telemetry`,
    onData: onSnapshot,
    onError,
  });
}
