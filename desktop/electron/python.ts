/**
 * Python sidecar lifecycle.
 *
 * The sidecar is a single-file PyInstaller bundle of `backend/app/main.py`.
 * Electron's main process spawns it on app startup, waits for /healthz to
 * succeed, and exposes the chosen port to the renderer via IPC.
 *
 * On packaged builds the binary lives at `process.resourcesPath/sidecar/sidecar`
 * (or `sidecar.exe` on Windows). In dev mode we fall back to
 * `python -m uvicorn app.main:app --port <port>` if the user has the backend
 * importable on the host Python — this is purely for hacking and never ships.
 */
import { spawn, type ChildProcess } from "node:child_process";
import { createServer } from "node:net";
import { existsSync } from "node:fs";
import { join } from "node:path";
import { app } from "electron";
import * as http from "node:http";

export interface SidecarHandle {
  port: number;
  proc: ChildProcess;
  baseUrl: string;
}

function pickFreePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const srv = createServer();
    srv.unref();
    srv.on("error", reject);
    srv.listen(0, "127.0.0.1", () => {
      const addr = srv.address();
      if (typeof addr !== "object" || addr === null) {
        reject(new Error("could not resolve listening address"));
        return;
      }
      const port = addr.port;
      srv.close(() => resolve(port));
    });
  });
}

function sidecarBinaryPath(): string | null {
  // In packaged builds, electron-builder copies python-sidecar/dist/sidecar
  // into process.resourcesPath/sidecar (see electron-builder.yml > extraResources).
  const exeName = process.platform === "win32" ? "sidecar.exe" : "sidecar";
  const packaged = join(process.resourcesPath ?? "", "sidecar", exeName);
  if (existsSync(packaged)) return packaged;

  // In `npm run dev:electron` (unpackaged) we look one level up at the
  // PyInstaller output directly. This is what the local AppImage smoke
  // test exercises.
  const local = join(app.getAppPath(), "python-sidecar", "dist", exeName);
  if (existsSync(local)) return local;

  return null;
}

async function waitForHealthz(port: number, timeoutMs: number): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  const url = `http://127.0.0.1:${port}/healthz`;
  let lastErr: unknown = null;
  while (Date.now() < deadline) {
    try {
      await new Promise<void>((resolve, reject) => {
        const req = http.get(url, (res) => {
          res.resume();
          if (res.statusCode === 200) resolve();
          else reject(new Error(`healthz returned ${res.statusCode}`));
        });
        req.on("error", reject);
        req.setTimeout(800, () => req.destroy(new Error("healthz timed out")));
      });
      return;
    } catch (err) {
      lastErr = err;
      await new Promise((r) => setTimeout(r, 250));
    }
  }
  throw new Error(
    `sidecar did not respond on ${url} within ${timeoutMs}ms (last error: ${String(lastErr)})`,
  );
}

export async function startSidecar(): Promise<SidecarHandle> {
  const port = await pickFreePort();
  const binary = sidecarBinaryPath();

  let proc: ChildProcess;
  const env = {
    ...process.env,
    CONET_DESKTOP_HOST: "127.0.0.1",
    CONET_DESKTOP_PORT: String(port),
    // Disable the backend's auth requirement when running embedded —
    // the renderer talks to a loopback-only sidecar that's never exposed.
    CONET_AUTH_REQUIRED: "false",
    CONET_ENVIRONMENT: "desktop",
  };

  if (binary) {
    proc = spawn(binary, [], {
      env,
      stdio: ["ignore", "pipe", "pipe"],
      windowsHide: true,
    });
  } else {
    // Dev-mode fallback. Requires `uvicorn` + the backend package on the
    // host's Python. Only used when running `npm run dev:electron` without
    // having built the PyInstaller bundle.
    const py = process.platform === "win32" ? "python" : "python3";
    proc = spawn(
      py,
      ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", String(port), "--log-level", "warning"],
      {
        env,
        cwd: join(app.getAppPath(), "..", "backend"),
        stdio: ["ignore", "pipe", "pipe"],
        windowsHide: true,
      },
    );
  }

  proc.stdout?.on("data", (buf) => process.stdout.write(`[sidecar] ${buf}`));
  proc.stderr?.on("data", (buf) => process.stderr.write(`[sidecar] ${buf}`));

  proc.on("exit", (code, signal) => {
    if (code !== null && code !== 0) {
      console.error(`[sidecar] exited with code ${code}`);
    } else if (signal !== null) {
      console.error(`[sidecar] killed by ${signal}`);
    }
  });

  try {
    await waitForHealthz(port, 15_000);
  } catch (err) {
    proc.kill("SIGTERM");
    throw err;
  }

  return { port, proc, baseUrl: `http://127.0.0.1:${port}` };
}

export function stopSidecar(handle: SidecarHandle | null): void {
  if (!handle) return;
  if (handle.proc.killed) return;
  handle.proc.kill("SIGTERM");
  // give it 2s to exit cleanly, then SIGKILL.
  setTimeout(() => {
    if (!handle.proc.killed) handle.proc.kill("SIGKILL");
  }, 2_000).unref();
}
