"""Build the LoRA fine-tuning corpus for the on-device QC sLLM.

The product's perception model (TacNet) emits a structured inspection record
per tray: each pill's integrated pressure, its deficit vs the good-pill
baseline, and a void verdict + confidence. The sLLM's job is to turn that
record into the operator-facing QC report shown on the Edge kiosk — a verdict,
which pills are flagged and *why* (a pressure/weight deficit consistent with a
sealed internal void that a camera cannot see), and a recommended action.

This script reads the labelled `.npz` dataset, reconstructs realistic inspection
records, and pairs each with a grounded report written in varied QC-operator
phrasings, producing a JSONL of {instruction, input, output} for SFT/LoRA.

Run:  python sim/isaac/sllm/build_corpus.py sim/dataset/tactile_pills.npz \
          --out sim/isaac/sllm/corpus.jsonl --trays 4000
"""
from __future__ import annotations

import argparse
import json
import os
import numpy as np

GRID = 4  # 4x4 pills per tray

INSTRUCTION = (
    "You are the QC inspector AI on a Conet Tactile Edge appliance. You receive "
    "a tactile inspection record from a 16x16 pressure mat under a pill tray. A "
    "sealed internal void makes a pill lighter, so it presses the mat less hard "
    "than the good-pill baseline — a defect a camera cannot see. From the record, "
    "write a concise QC report: overall verdict, flagged pills with their grid "
    "position and pressure deficit, the physical reason, and the recommended "
    "action."
)


def _pos(k):
    return f"R{k // GRID + 1}C{k % GRID + 1}"


def make_record(press, lab, mu, sigma, line="LINE-01", tray_id=1, conf=None):
    """Build the structured input record the perception layer would emit."""
    pills = []
    for k in range(len(press)):
        deficit = (mu - press[k]) / mu * 100.0
        z = (mu - press[k]) / max(sigma, 1e-9)
        verdict = "VOID" if lab[k] == 1 else "OK"
        c = conf[k] if conf is not None else min(0.999, max(0.5, 1 / (1 + np.exp(-(z - 2.5)))))
        pills.append(dict(pos=_pos(k), pressure=round(float(press[k]), 3),
                          deficit_pct=round(float(deficit), 1),
                          z=round(float(z), 2), verdict=verdict,
                          confidence=round(float(c), 3)))
    n_void = int(lab.sum())
    rec = dict(line=line, tray=tray_id, mat="16x16", n_pills=len(press),
               baseline_mean=round(float(mu), 3), baseline_sigma=round(float(sigma), 3),
               flagged=n_void, pills=pills)
    return rec


def _fmt_input(rec):
    lines = [f"line={rec['line']} tray={rec['tray']} mat={rec['mat']} "
             f"baseline={rec['baseline_mean']}+/-{rec['baseline_sigma']}N"]
    for p in rec["pills"]:
        lines.append(f"  {p['pos']}: P={p['pressure']}N deficit={p['deficit_pct']}% "
                     f"z={p['z']} -> {p['verdict']} ({p['confidence']:.2f})")
    return "\n".join(lines)


def make_report(rec, rng):
    """A grounded, varied QC report for the record."""
    flagged = [p for p in rec["pills"] if p["verdict"] == "VOID"]
    n = rec["n_pills"]
    if not flagged:
        openers = [
            f"PASS — all {n} pills within tolerance.",
            f"Tray {rec['tray']}: PASS. {n}/{n} pills nominal.",
            f"Verdict: PASS. No pressure deficit detected across the {n}-pill tray.",
        ]
        tails = [
            f"Every pill loads the mat near the {rec['baseline_mean']} N baseline; no internal void signature.",
            "Pressure field uniform; weight consistent with solid fill. Release tray.",
            "No camera-invisible mass deficit found. Continue line.",
        ]
        return rng.choice(openers) + " " + rng.choice(tails)

    poss = ", ".join(f"{p['pos']} (-{p['deficit_pct']:.0f}%)" for p in flagged)
    worst = max(flagged, key=lambda p: p["deficit_pct"])
    openers = [
        f"REJECT — {len(flagged)} of {n} pills show a void signature.",
        f"Tray {rec['tray']}: FAIL. {len(flagged)} suspected internal void(s).",
        f"Verdict: REJECT. Tactile deficit on {len(flagged)} pill(s).",
    ]
    reason = rng.choice([
        f"Flagged pills press the mat {worst['deficit_pct']:.0f}% below the "
        f"{rec['baseline_mean']} N baseline — a weight deficit consistent with a sealed "
        "internal cavity, which is externally identical and invisible to vision.",
        "The low-pressure patches indicate lighter pills (internal void); the outer "
        "shell is intact so an optical/Cognex check would pass them.",
        f"Pressure shortfall (worst {worst['pos']}, z={worst['z']}) matches the void "
        "physics: same geometry, reduced mass, lower contact load.",
    ])
    action = rng.choice([
        f"Divert {poss} to the reject bin and log the lot.",
        f"Eject the flagged cells ({poss}); hold the lot for QA review.",
        f"Actuate reject for {poss}; flag batch for re-sampling.",
    ])
    return f"{rng.choice(openers)} Flagged: {poss}. {reason} {action}"


def build(npz_path, out_path, n_trays=4000, seed=0):
    d = np.load(npz_path)
    press = d["pill_pressure"].astype(float)
    lab = d["pill_label"].astype(int)
    # global good-pill baseline (what the device calibrates against)
    mu = press[lab == 0].mean(); sigma = press[lab == 0].std()
    rng = np.random.default_rng(seed)
    n_avail = press.shape[0]
    pick = rng.choice(n_avail, size=min(n_trays, n_avail), replace=False)

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    n_pos = n_neg = 0
    with open(out_path, "w") as f:
        for i, t in enumerate(pick):
            rec = make_record(press[t], lab[t], mu, sigma, tray_id=int(t))
            report = make_report(rec, rng)
            n_pos += rec["flagged"] > 0
            n_neg += rec["flagged"] == 0
            f.write(json.dumps(dict(instruction=INSTRUCTION,
                                    input=_fmt_input(rec),
                                    output=report)) + "\n")
    print(f"[corpus] wrote {len(pick)} examples -> {out_path} "
          f"({n_pos} reject / {n_neg} pass)  baseline={mu:.3f}+/-{sigma:.3f}N")
    return out_path


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("npz", nargs="?", default="sim/dataset/tactile_pills.npz")
    ap.add_argument("--out", default="sim/isaac/sllm/corpus.jsonl")
    ap.add_argument("--trays", type=int, default=4000)
    a = ap.parse_args()
    build(a.npz, a.out, a.trays)
