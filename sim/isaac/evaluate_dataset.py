"""Evaluate an Isaac/MuJoCo tactile pill dataset with the existing detector."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from sim.generate_dataset import metrics


REQUIRED_KEYS = ("frames", "pill_pressure", "pill_label", "pill_centers")


def _load(path: Path) -> dict[str, np.ndarray]:
    with np.load(path) as data:
        missing = [key for key in REQUIRED_KEYS if key not in data]
        if missing:
            raise SystemExit(f"missing dataset keys: {', '.join(missing)}")
        return {key: data[key] for key in REQUIRED_KEYS}


def evaluate(path: Path) -> dict[str, float | int]:
    dataset = _load(path)
    frames = dataset["frames"]
    pill_pressure = dataset["pill_pressure"]
    pill_label = dataset["pill_label"]

    if frames.ndim != 3 or frames.shape[1:] != (16, 16):
        raise SystemExit(f"frames must have shape (N,16,16), got {frames.shape}")
    if pill_pressure.shape != pill_label.shape or pill_pressure.shape[1:] != (16,):
        raise SystemExit(
            "pill_pressure and pill_label must both have shape (N,16), got "
            f"{pill_pressure.shape} and {pill_label.shape}"
        )

    result = metrics(pill_pressure, pill_label)
    good = pill_pressure[pill_label == 0]
    void = pill_pressure[pill_label == 1]
    return {
        **result,
        "trays": int(frames.shape[0]),
        "pills": int(pill_label.size),
        "void": int(pill_label.sum()),
        "good_mean": float(good.mean()),
        "good_std": float(good.std()),
        "void_mean": float(void.mean()),
        "void_std": float(void.std()),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    args = parser.parse_args()

    result = evaluate(args.dataset)
    print("TACTILE VOID-DETECTION DATASET EVAL")
    print(f"dataset: {result['trays']} trays, {result['pills']} pills")
    print(f"void pills: {result['void']}")
    print(f"good pressure: {result['good_mean']:.3f} +/- {result['good_std']:.3f} N")
    print(f"void pressure: {result['void_mean']:.3f} +/- {result['void_std']:.3f} N")
    print(f"ROC-AUC: {result['auc'] * 100:.2f}%")
    print(
        "accuracy: "
        f"{result['acc'] * 100:.2f}% | precision {result['prec'] * 100:.2f}% | "
        f"recall {result['rec'] * 100:.2f}% | F1 {result['f1'] * 100:.2f}%"
    )
    print(
        f"confusion: TP={result['tp']} FP={result['fp']} "
        f"FN={result['fn']} TN={result['tn']}"
    )


if __name__ == "__main__":
    main()
