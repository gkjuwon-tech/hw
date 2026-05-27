"""Export the QC sLLM for the Jetson Orin Nano edge box.

1. merge the LoRA adapter into the base weights (a standalone model)
2. convert to GGUF and quantize to INT4 (Q4_K_M) via llama.cpp if available —
   the format the Orin Nano runs in real time (llama.cpp CUDA / ollama). If the
   llama.cpp tools are not present, the merged HF model is still written and the
   exact conversion commands are printed.
3. write an edge deployment manifest (runtime, quant, memory, latency budget).

On the Orin Nano 8 GB the perception model (TacNet, ONNX->TensorRT) does the
real-time per-pill detection; this INT4 sLLM (~0.5B) writes the QC report only
when a tray is flagged, well inside the line's per-tray time budget.

Run:  python sim/isaac/sllm/export_edge.py --adapter sim/isaac/sllm/adapter \
          --out sim/isaac/sllm/edge
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess


def merge(model_id, adapter, out_merged):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel
    print(f"[export] merging adapter {adapter} into {model_id}")
    base = AutoModelForCausalLM.from_pretrained(model_id, torch_dtype=torch.float16)
    model = PeftModel.from_pretrained(base, adapter)
    model = model.merge_and_unload()
    os.makedirs(out_merged, exist_ok=True)
    model.save_pretrained(out_merged)
    AutoTokenizer.from_pretrained(adapter).save_pretrained(out_merged)
    return out_merged


def to_gguf_int4(merged, out_dir):
    """Convert + quantize via llama.cpp if its tools are on PATH/cloned."""
    llama = os.environ.get("LLAMA_CPP", "/workspace/llama.cpp")
    conv = os.path.join(llama, "convert_hf_to_gguf.py")
    quant = os.path.join(llama, "llama-quantize")
    f16 = os.path.join(out_dir, "qc-sllm-f16.gguf")
    q4 = os.path.join(out_dir, "qc-sllm-Q4_K_M.gguf")
    if not os.path.exists(conv):
        print(f"[export] llama.cpp not found at {llama}; skipping GGUF. "
              f"To build: git clone https://github.com/ggerganov/llama.cpp {llama} "
              f"&& cmake -B {llama}/build {llama} && cmake --build {llama}/build -j")
        print(f"[export] then: python {conv} {merged} --outfile {f16} --outtype f16 "
              f"&& {quant} {f16} {q4} Q4_K_M")
        return None
    subprocess.run(["python", conv, merged, "--outfile", f16, "--outtype", "f16"], check=True)
    qbin = quant if os.path.exists(quant) else os.path.join(llama, "build", "bin", "llama-quantize")
    subprocess.run([qbin, f16, q4, "Q4_K_M"], check=True)
    print(f"[export] INT4 GGUF -> {q4}")
    return q4


def write_manifest(out_dir, model_id, gguf, merged):
    sz = os.path.getsize(gguf) / 1e6 if gguf and os.path.exists(gguf) else None
    manifest = {
        "product": "Conet Tactile Edge — on-device QC AI",
        "edge_device": "NVIDIA Jetson Orin Nano 8GB (40 TOPS, 7-15 W)",
        "pipeline": [
            {"stage": "perception", "model": "TacNet (CNN)",
             "format": "ONNX -> TensorRT (FP16)", "role": "real-time per-pill void detection",
             "runs": "every tray"},
            {"stage": "reporting", "model": os.path.basename(model_id),
             "format": "GGUF Q4_K_M (INT4)", "runtime": "llama.cpp CUDA / ollama",
             "role": "operator QC report on flagged trays", "runs": "on reject only"},
        ],
        "sllm_gguf": os.path.basename(gguf) if gguf else None,
        "sllm_gguf_mb": round(sz, 1) if sz else None,
        "memory_budget_gb": 8,
        "notes": "INT4 0.5B fits in <0.6 GB; report generation (~120 tokens) is "
                 "well under the per-tray time budget at 0.15 m/s belt speed.",
    }
    path = os.path.join(out_dir, "edge_manifest.json")
    with open(path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"[export] wrote {path}")
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="Qwen/Qwen2.5-0.5B-Instruct")
    ap.add_argument("--adapter", default="sim/isaac/sllm/adapter")
    ap.add_argument("--out", default="sim/isaac/sllm/edge")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    merged = merge(a.model, a.adapter, os.path.join(a.out, "merged"))
    gguf = to_gguf_int4(merged, a.out)
    write_manifest(a.out, a.model, gguf, merged)
    print("[export] done")


if __name__ == "__main__":
    main()
