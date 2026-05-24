/**
 * Server-Sent Events subscriber for inspection events.
 *
 * EventSource is available globally in Chromium (which Electron's renderer
 * is). The sidecar exposes `/v1/lines/{id}/events` returning
 * `text/event-stream`; we forward each parsed JSON payload to the caller's
 * `onEvent` callback. The subscriber auto-retries with capped exponential
 * backoff on the connection dropping — the FastAPI bus is otherwise
 * stateless and any restart returns a fresh stream.
 */

import type { InspectionEvent } from "./types";
import { apiBaseUrl } from "./api";

export interface Subscription {
  close: () => void;
}

export async function subscribeLineEvents(
  lineId: string,
  onEvent: (e: InspectionEvent) => void,
  onError?: (err: Error) => void,
): Promise<Subscription> {
  const base = await apiBaseUrl();
  let es: EventSource | null = null;
  let closed = false;
  let backoffMs = 500;

  const connect = (): void => {
    if (closed) return;
    es = new EventSource(`${base}/v1/lines/${encodeURIComponent(lineId)}/events`);
    es.onopen = () => {
      backoffMs = 500;
    };
    es.onmessage = (msg) => {
      try {
        const data = JSON.parse(msg.data) as InspectionEvent;
        onEvent(data);
      } catch {
        // Ignore non-JSON keepalive frames.
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
