"""Procedural PBR texture maps for the Isaac-Sim digital twin.

We do not ship binary texture assets in the repo. Every map (diffuse, roughness,
normal) is generated deterministically into ``sim/isaac/assets/tex/`` on first
import, then cached on disk. The scene then binds those PNGs into OmniPBR
material inputs so factory floor / belt / aluminium / steel / Velostat / PCB
all read as real materials under RTX, not flat colour swatches.

Maps are 1024x1024 unless stated otherwise; numbers are tuned against real
references, not random.
"""
from __future__ import annotations

import os

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
TEX_DIR = os.path.join(HERE, "assets", "tex")
os.makedirs(TEX_DIR, exist_ok=True)


# ── helpers ────────────────────────────────────────────────────────────────

def _save(path: str, arr: np.ndarray) -> str:
    if arr.ndim == 2:
        arr = np.stack([arr] * 3, axis=-1)
    Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).save(path, optimize=True)
    return path


def _normal_from_height(h: np.ndarray, strength: float = 2.0) -> np.ndarray:
    """Tangent-space normal map from a height field. Output in 0..255 (RGB)."""
    gy, gx = np.gradient(h.astype(np.float32))
    nz = np.ones_like(gx)
    n = np.stack([-gx * strength, -gy * strength, nz], axis=-1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True) + 1e-6
    return ((n * 0.5 + 0.5) * 255).astype(np.uint8)


def _bilinear_upsample(coarse: np.ndarray, size: int) -> np.ndarray:
    """Periodic bilinear upsample of `coarse` to (size, size). No external deps."""
    n = coarse.shape[0]
    s = np.linspace(0, n, size, endpoint=False, dtype=np.float32)
    i0 = np.floor(s).astype(np.int32) % n
    i1 = (i0 + 1) % n
    fr = (s - np.floor(s)).astype(np.float32)
    a = coarse[i0[:, None], i0[None, :]]
    b = coarse[i0[:, None], i1[None, :]]
    c = coarse[i1[:, None], i0[None, :]]
    d = coarse[i1[:, None], i1[None, :]]
    fx = fr[None, :]
    fy = fr[:, None]
    return (a * (1 - fx) * (1 - fy) + b * fx * (1 - fy)
            + c * (1 - fx) * fy + d * fx * fy)


def _value_noise(size: int, octaves: int, seed: int = 0,
                 persistence: float = 0.5) -> np.ndarray:
    """Plain fBm value noise in [0, 1] with smooth bilinear upsampling."""
    rng = np.random.default_rng(seed)
    out = np.zeros((size, size), dtype=np.float32)
    amp = 1.0
    total = 0.0
    for o in range(octaves):
        n = max(2, 2 ** (o + 2))
        coarse = rng.random((n, n), dtype=np.float32)
        big = _bilinear_upsample(coarse, size)
        out += big * amp
        total += amp
        amp *= persistence
    return out / total


def _row_brushed(size: int, intensity: float = 0.06, seed: int = 1) -> np.ndarray:
    """One vertical column of noise stretched horizontally — brushed metal grain."""
    rng = np.random.default_rng(seed)
    col = rng.normal(0.0, 1.0, size).astype(np.float32)
    # gentle low-pass so brush strokes are continuous
    for _ in range(3):
        col = (col + np.roll(col, 1) + np.roll(col, -1)) / 3.0
    grain = np.tile(col[:, None], (1, size))
    # add a much finer cross-noise so it's not pure stripes
    fine = rng.normal(0.0, 0.25, (size, size)).astype(np.float32)
    return (grain + fine) * intensity


# ── individual materials ───────────────────────────────────────────────────

def concrete_sweep(size: int = 2048, force: bool = False) -> dict:
    """Polished factory concrete — floor sweep. Light cool grey, subtle dust
    speckle + faint troweling, polished-clear roughness in [0.32, 0.45]."""
    out = {
        "diffuse": os.path.join(TEX_DIR, "concrete_d.png"),
        "rough":   os.path.join(TEX_DIR, "concrete_r.png"),
        "normal":  os.path.join(TEX_DIR, "concrete_n.png"),
    }
    if not force and all(os.path.exists(p) for p in out.values()):
        return out

    rng = np.random.default_rng(7)
    base = 0.74  # luminance of polished concrete under daylight
    n_lo = _value_noise(size, octaves=5, seed=3, persistence=0.55)   # macro stains
    n_hi = _value_noise(size, octaves=3, seed=4, persistence=0.45)   # micro speckle
    lum = base + (n_lo - 0.5) * 0.05 + (n_hi - 0.5) * 0.04
    speckle = rng.random((size, size)) < 0.0006
    lum -= speckle * 0.18
    # gentle cool tint
    diffuse = np.stack([lum * 0.97, lum * 0.99, lum * 1.02], axis=-1) * 255
    _save(out["diffuse"], diffuse)

    rough = 0.36 + (n_lo - 0.5) * 0.08 + (n_hi - 0.5) * 0.04
    _save(out["rough"], rough * 255)

    height = (n_lo * 0.7 + n_hi * 0.3) * 0.6
    _save(out["normal"], _normal_from_height(height, strength=0.5))
    return out


def pu_belt(size: int = 1024, force: bool = False) -> dict:
    """Dark food-grade PU/PVC conveyor belt: very dark grey, slight grain, low
    gloss with a faint streak along the run direction."""
    out = {
        "diffuse": os.path.join(TEX_DIR, "belt_d.png"),
        "rough":   os.path.join(TEX_DIR, "belt_r.png"),
        "normal":  os.path.join(TEX_DIR, "belt_n.png"),
    }
    if not force and all(os.path.exists(p) for p in out.values()):
        return out
    base = 0.055
    micro = _value_noise(size, octaves=4, seed=11, persistence=0.4) - 0.5
    streak = _row_brushed(size, intensity=0.012, seed=12)
    lum = base + micro * 0.03 + streak
    diffuse = np.stack([lum * 1.0, lum * 1.02, lum * 1.04], axis=-1) * 255
    _save(out["diffuse"], diffuse)

    rough = 0.55 + micro * 0.05
    _save(out["rough"], rough * 255)

    height = micro * 0.6 + streak * 6.0
    _save(out["normal"], _normal_from_height(height, strength=1.0))
    return out


def brushed_alu(size: int = 1024, force: bool = False) -> dict:
    """Anodized brushed aluminium — frames, bezel, stand. Cool neutral grey,
    crisp horizontal brush direction so it reads as machined metal at any angle."""
    out = {
        "diffuse": os.path.join(TEX_DIR, "alu_d.png"),
        "rough":   os.path.join(TEX_DIR, "alu_r.png"),
        "normal":  os.path.join(TEX_DIR, "alu_n.png"),
    }
    if not force and all(os.path.exists(p) for p in out.values()):
        return out
    base = 0.78
    brush = _row_brushed(size, intensity=0.05, seed=21)
    micro = _value_noise(size, octaves=2, seed=22, persistence=0.4) - 0.5
    lum = base + brush + micro * 0.01
    diffuse = np.stack([lum * 0.99, lum * 1.0, lum * 1.02], axis=-1) * 255
    _save(out["diffuse"], diffuse)

    rough = 0.22 + brush * 1.2 + (micro * 0.02)
    _save(out["rough"], rough * 255)

    # mostly directional brush strokes
    _save(out["normal"], _normal_from_height(brush * 3.0 + micro * 0.2, strength=2.5))
    return out


def stainless(size: int = 1024, force: bool = False) -> dict:
    """Polished stainless steel for rollers and rails. Higher reflectivity,
    finer brush direction, slightly warmer than alu."""
    out = {
        "diffuse": os.path.join(TEX_DIR, "steel_d.png"),
        "rough":   os.path.join(TEX_DIR, "steel_r.png"),
        "normal":  os.path.join(TEX_DIR, "steel_n.png"),
    }
    if not force and all(os.path.exists(p) for p in out.values()):
        return out
    base = 0.86
    brush = _row_brushed(size, intensity=0.025, seed=31)
    micro = _value_noise(size, octaves=2, seed=32, persistence=0.4) - 0.5
    lum = base + brush + micro * 0.006
    diffuse = np.stack([lum * 1.0, lum * 1.0, lum * 1.0], axis=-1) * 255
    _save(out["diffuse"], diffuse)
    rough = 0.18 + brush * 0.6 + micro * 0.01
    _save(out["rough"], rough * 255)
    _save(out["normal"], _normal_from_height(brush * 1.5 + micro * 0.15, strength=1.4))
    return out


def velostat(size: int = 1024, force: bool = False) -> dict:
    """Velostat tactile mat: dark teal/black piezoresistive film. Subtle weave
    micro-texture, low-medium gloss. The 10 mm cell grid is drawn separately
    in scene geometry, not baked in here."""
    out = {
        "diffuse": os.path.join(TEX_DIR, "velostat_d.png"),
        "rough":   os.path.join(TEX_DIR, "velostat_r.png"),
        "normal":  os.path.join(TEX_DIR, "velostat_n.png"),
    }
    if not force and all(os.path.exists(p) for p in out.values()):
        return out
    # very fine cross-weave at ~150 dpi-equivalent: 4 px period
    yy, xx = np.mgrid[0:size, 0:size]
    weave = (np.sin(xx * np.pi / 3.0) + np.sin(yy * np.pi / 3.0)) * 0.5
    micro = _value_noise(size, octaves=3, seed=41, persistence=0.45) - 0.5
    base = 0.07
    lum = base + weave * 0.012 + micro * 0.02
    # cool teal tint
    diffuse = np.stack([lum * 0.4, lum * 1.4, lum * 1.1], axis=-1) * 255
    _save(out["diffuse"], diffuse)
    rough = 0.55 + micro * 0.05 - weave * 0.02
    _save(out["rough"], rough * 255)
    height = weave * 0.5 + micro * 0.2
    _save(out["normal"], _normal_from_height(height, strength=1.6))
    return out


def graphite(size: int = 1024, force: bool = False) -> dict:
    """3D-print PETG matte graphite — the kiosk body. Layer lines are scoped
    by the bezel anyway; we just need a deep grey with micro-roughness."""
    out = {
        "diffuse": os.path.join(TEX_DIR, "graphite_d.png"),
        "rough":   os.path.join(TEX_DIR, "graphite_r.png"),
        "normal":  os.path.join(TEX_DIR, "graphite_n.png"),
    }
    if not force and all(os.path.exists(p) for p in out.values()):
        return out
    micro = _value_noise(size, octaves=3, seed=51, persistence=0.5) - 0.5
    # subtle layer-line stripe along Z (rendered horizontally on print)
    yy = np.arange(size)[:, None]
    layer = np.sin(yy * np.pi / 4.0) * 0.5
    layer = np.tile(layer, (1, size))
    base = 0.045
    lum = base + micro * 0.01 + layer * 0.004
    diffuse = np.stack([lum * 1.0, lum * 1.02, lum * 1.08], axis=-1) * 255
    _save(out["diffuse"], diffuse)
    rough = 0.55 + micro * 0.04 + layer * 0.02
    _save(out["rough"], rough * 255)
    _save(out["normal"], _normal_from_height(layer * 0.6 + micro * 0.3, strength=0.8))
    return out


def pcb_green(size: int = 1024, force: bool = False) -> dict:
    """Green PCB solder mask with subtle silk traces. Single 'top-side' look,
    no specific layout — used to dress the scanner PCB on the belt and the
    Jetson carrier inside the kiosk."""
    out = {
        "diffuse": os.path.join(TEX_DIR, "pcb_d.png"),
        "rough":   os.path.join(TEX_DIR, "pcb_r.png"),
        "normal":  os.path.join(TEX_DIR, "pcb_n.png"),
    }
    if not force and all(os.path.exists(p) for p in out.values()):
        return out
    rng = np.random.default_rng(61)
    # base solder mask: deep green
    img = np.zeros((size, size, 3), dtype=np.float32)
    img[..., 0] = 18 / 255
    img[..., 1] = 76 / 255
    img[..., 2] = 36 / 255
    # silk traces: random copper lines (lighter shade), L-shaped routes
    trace = np.zeros((size, size), dtype=np.float32)
    for _ in range(220):
        x0 = rng.integers(0, size)
        y0 = rng.integers(0, size)
        length = rng.integers(40, 260)
        width = rng.integers(2, 5)
        horiz = rng.random() < 0.5
        if horiz:
            trace[y0:y0 + width, x0:x0 + length] = 1.0
        else:
            trace[y0:y0 + length, x0:x0 + width] = 1.0
    # vias: small bright dots
    vias = np.zeros((size, size), dtype=np.float32)
    for _ in range(140):
        x = rng.integers(8, size - 8)
        y = rng.integers(8, size - 8)
        r = rng.integers(3, 6)
        yy, xx = np.ogrid[:size, :size]
        m = (xx - x) ** 2 + (yy - y) ** 2 < r ** 2
        vias[m] = 1.0
    # silk-screen labels (just rectangles of "silkscreen white")
    silk = np.zeros((size, size), dtype=np.float32)
    for _ in range(30):
        x = rng.integers(0, size - 32)
        y = rng.integers(0, size - 12)
        w = rng.integers(12, 30)
        h = rng.integers(4, 8)
        silk[y:y + h, x:x + w] = 1.0
    # blend
    copper_tint = np.array([0.78, 0.55, 0.20])  # tinned copper
    silk_tint   = np.array([0.96, 0.97, 0.99])
    for c in range(3):
        img[..., c] = img[..., c] * (1 - trace) + trace * copper_tint[c]
        img[..., c] = img[..., c] * (1 - vias)  + vias  * 0.75
        img[..., c] = img[..., c] * (1 - silk * 0.5) + silk_tint[c] * silk * 0.5
    micro = _value_noise(size, octaves=2, seed=62, persistence=0.4) - 0.5
    img += micro[..., None] * 0.02
    _save(out["diffuse"], img * 255)

    rough = 0.38 + (1 - trace) * 0.05 - trace * 0.15 - vias * 0.2
    _save(out["rough"], rough * 255)
    _save(out["normal"], _normal_from_height(trace * 0.4 + vias * 0.6, strength=0.5))
    return out


def pill_white(size: int = 512, force: bool = False) -> dict:
    """Pharmaceutical tablet — slightly powdery off-white with micro-variation."""
    out = {
        "diffuse": os.path.join(TEX_DIR, "pill_d.png"),
        "rough":   os.path.join(TEX_DIR, "pill_r.png"),
    }
    if not force and all(os.path.exists(p) for p in out.values()):
        return out
    micro = _value_noise(size, octaves=3, seed=71, persistence=0.4) - 0.5
    base = 0.93
    lum = base + micro * 0.02
    diffuse = np.stack([lum, lum * 0.995, lum * 0.985], axis=-1) * 255
    _save(out["diffuse"], diffuse)
    rough = 0.42 + micro * 0.06
    _save(out["rough"], rough * 255)
    return out


# ── studio HDRI fallback (when /workspace/hdri.hdr is missing) ─────────────

def studio_dome_hdr(size: int = 1024, force: bool = False) -> str:
    """A neutral seamless studio gradient HDR used as the dome texture if a real
    factory HDRI isn't present. Goes from clean upper sky down to the warm
    horizon line that the cyclorama sweep blends into."""
    path = os.path.join(TEX_DIR, "studio_dome.hdr")
    if not force and os.path.exists(path):
        return path
    h, w = size // 2, size
    yy = np.arange(h, dtype=np.float32)[:, None]
    t = yy / max(h - 1, 1)                                   # 0 = top, 1 = horizon
    # cool upper sky -> warmer ground (so the floor's lower-bounce reads warm)
    top = np.array([0.62, 0.70, 0.86]) * 1.05
    mid = np.array([0.85, 0.88, 0.95]) * 1.00
    bot = np.array([0.55, 0.50, 0.46]) * 0.90
    upper = top + (mid - top) * t
    lower = mid + (bot - mid) * t
    sky = np.where(t < 0.5, upper, lower)
    img = np.broadcast_to(sky[:, None, :], (h, w, 3)).astype(np.float32)
    # write as .hdr (Radiance RGBE) so dome lights can ingest it
    _write_hdr(path, img)
    return path


def _write_hdr(path: str, rgb: np.ndarray) -> None:
    """Minimal Radiance .hdr (RGBE) writer. `rgb` is float32, linear."""
    h, w = rgb.shape[:2]
    rgb = np.clip(rgb, 0.0, None)
    max_c = rgb.max(axis=-1)
    nonzero = max_c > 1e-32
    mantissa = np.zeros_like(rgb)
    exponent = np.zeros((h, w), dtype=np.int32)
    if nonzero.any():
        m, e = np.frexp(max_c[nonzero])
        mantissa[nonzero] = rgb[nonzero] * (m * 256.0 / max_c[nonzero])[..., None]
        exponent[nonzero] = e + 128
    rgbe = np.zeros((h, w, 4), dtype=np.uint8)
    rgbe[..., :3] = np.clip(mantissa, 0, 255).astype(np.uint8)
    rgbe[..., 3] = np.clip(exponent, 0, 255).astype(np.uint8)
    with open(path, "wb") as f:
        f.write(b"#?RADIANCE\n")
        f.write(b"FORMAT=32-bit_rle_rgbe\n\n")
        f.write(f"-Y {h} +X {w}\n".encode())
        f.write(rgbe.tobytes())


# ── one-shot bundle ────────────────────────────────────────────────────────

def ensure_all(force: bool = False) -> dict:
    """Generate the full PBR set used by sim/isaac/scene.py. Returns a dict
    keyed by material name with dicts of {diffuse, rough, normal[, ...]}."""
    return {
        "concrete":  concrete_sweep(force=force),
        "belt":      pu_belt(force=force),
        "alu":       brushed_alu(force=force),
        "steel":     stainless(force=force),
        "velostat":  velostat(force=force),
        "graphite":  graphite(force=force),
        "pcb":       pcb_green(force=force),
        "pill":      pill_white(force=force),
    }


if __name__ == "__main__":
    out = ensure_all(force=True)
    for name, paths in out.items():
        print(name, paths)
