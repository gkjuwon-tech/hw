/**
 * Electron main process.
 *
 *   on app.ready:
 *     1. start the Python sidecar (FastAPI backend bundled by PyInstaller)
 *     2. create the dashboard BrowserWindow
 *     3. expose `window.conet.apiBase` to the renderer via contextBridge
 *
 *   on window-all-closed (or before-quit):
 *     SIGTERM the sidecar, fall back to SIGKILL after 2s.
 */
import { app, BrowserWindow, ipcMain, shell } from "electron";
import { join } from "node:path";
import { startSidecar, stopSidecar, type SidecarHandle } from "./python";

let sidecar: SidecarHandle | null = null;
let mainWindow: BrowserWindow | null = null;

function rendererEntry(): string {
  // In dev (`npm run dev`), Vite serves the renderer at :5173 with HMR.
  // In packaged builds, electron-builder ships the static bundle at
  // `dist/index.html` next to this file inside the asar.
  if (process.env.CONET_DEV_RENDERER === "1") return "http://localhost:5173";
  return `file://${join(__dirname, "..", "dist", "index.html")}`;
}

async function createWindow(): Promise<void> {
  mainWindow = new BrowserWindow({
    width: 1320,
    height: 880,
    minWidth: 1024,
    minHeight: 700,
    backgroundColor: "#f5f5f1",
    title: "Conet Tactile",
    autoHideMenuBar: true,
    webPreferences: {
      preload: join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
    show: false,
  });

  // Open external links in the user's default browser rather than a new
  // BrowserWindow. Keeps the desktop surface tight.
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    void shell.openExternal(url);
    return { action: "deny" };
  });

  mainWindow.once("ready-to-show", () => {
    mainWindow?.show();
  });

  await mainWindow.loadURL(rendererEntry());
}

app.whenReady().then(async () => {
  try {
    sidecar = await startSidecar();
  } catch (err) {
    console.error("[main] failed to start sidecar:", err);
    app.exit(1);
    return;
  }

  ipcMain.handle("conet:getApiBase", () => sidecar?.baseUrl ?? null);
  ipcMain.handle("conet:openExternal", async (_, url: string) => {
    if (typeof url !== "string") return;
    if (!/^https?:\/\//.test(url)) return;
    await shell.openExternal(url);
  });

  await createWindow();
});

app.on("window-all-closed", () => {
  // macOS convention is to keep the app running even with no windows, but
  // this is an industrial tool — closing the dashboard means the operator
  // is done. We quit on all platforms.
  app.quit();
});

app.on("before-quit", () => {
  stopSidecar(sidecar);
  sidecar = null;
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    void createWindow();
  }
});
