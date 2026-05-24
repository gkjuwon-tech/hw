"""PyInstaller entry point for the embedded FastAPI backend.

This is what becomes `dist/sidecar` (or `sidecar.exe` on Windows) after
`pyinstaller sidecar.spec`. The bundle is placed inside the packaged
Electron app's `resources/sidecar/` directory and spawned by the main
process at startup.

The launcher honors two environment variables that the Electron main
process sets:

  CONET_DESKTOP_HOST  defaults to 127.0.0.1
  CONET_DESKTOP_PORT  defaults to 8765

It binds the FastAPI app to that host/port using uvicorn's programmatic
API (uvicorn.run) so we never depend on the CLI being on PATH inside the
frozen bundle.
"""

from __future__ import annotations

import os
import sys


def _main() -> int:
    host = os.environ.get("CONET_DESKTOP_HOST", "127.0.0.1")
    port_str = os.environ.get("CONET_DESKTOP_PORT", "8765")
    try:
        port = int(port_str)
    except ValueError:
        print(
            f"[sidecar] CONET_DESKTOP_PORT={port_str!r} is not an integer",
            file=sys.stderr,
        )
        return 64

    # Imported lazily so PyInstaller can pick up the actual modules used,
    # not the side effects of importing the world at startup.
    import uvicorn

    from app.main import app

    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="warning",
        access_log=False,
        # The sidecar is loopback-only — no proxy headers, no forwarding.
        proxy_headers=False,
        # PyInstaller frozen apps can't reload themselves anyway.
        reload=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
