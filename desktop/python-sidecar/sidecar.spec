# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for the Conet Tactile desktop sidecar.
#
# Build with:
#   pip install pyinstaller
#   pip install -e ../../backend
#   pyinstaller --noconfirm --clean python-sidecar/sidecar.spec
#
# Output:
#   python-sidecar/dist/sidecar       (Linux/macOS ELF/Mach-O)
#   python-sidecar/dist/sidecar.exe   (Windows)
#
# The output binary is placed inside the packaged Electron app at
# `resources/sidecar/` via electron-builder.yml > extraResources.

from __future__ import annotations

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

HERE = Path(SPECPATH).resolve()
BACKEND = (HERE.parent.parent / "backend").resolve()
sys.path.insert(0, str(BACKEND))

# uvicorn + fastapi pull in plugin-style dependencies that PyInstaller
# can't always discover by static analysis. We collect them explicitly.
hidden = [
    *collect_submodules("uvicorn"),
    *collect_submodules("uvicorn.protocols"),
    *collect_submodules("uvicorn.loops"),
    *collect_submodules("uvicorn.lifespan"),
    *collect_submodules("anyio"),
    *collect_submodules("sniffio"),
    *collect_submodules("fastapi"),
    *collect_submodules("starlette"),
    *collect_submodules("pydantic"),
    *collect_submodules("pydantic_core"),
    *collect_submodules("sqlalchemy.dialects.sqlite"),
    *collect_submodules("aiosqlite"),
    *collect_submodules("app"),
]

a = Analysis(
    [str(HERE / "launcher.py")],
    pathex=[str(BACKEND)],
    binaries=[],
    datas=[],
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "PyQt5", "PyQt6", "PySide6"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="sidecar",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
