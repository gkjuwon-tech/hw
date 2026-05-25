/**
 * Renderer-visible API. Exposed on `window.conet` via contextBridge so the
 * renderer never sees raw Node primitives. Keep this surface deliberately
 * thin — anything richer should go through the FastAPI sidecar over HTTP.
 */
import { contextBridge, ipcRenderer } from "electron";

const api = {
  /** Returns `http://127.0.0.1:<port>` for the sidecar, or `null` on dev fallback. */
  getApiBase: (): Promise<string | null> => ipcRenderer.invoke("conet:getApiBase"),

  /** Open a URL in the user's default browser (https/http only). */
  openExternal: (url: string): Promise<void> => ipcRenderer.invoke("conet:openExternal", url),

  /** Build metadata so the renderer can show the right version string. */
  platform: process.platform,
};

contextBridge.exposeInMainWorld("conet", api);

export type ConetBridge = typeof api;
