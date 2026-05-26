"""Run the fine-tuned QC sLLM — turn an inspection record into an operator report.

Loads the base model + the LoRA adapter and generates the report exactly as the
Edge appliance would on the kiosk display. With --demo it pulls a few trays from
the dataset, runs the perception baseline to build the record, and prints the
record alongside the model's report.

Run:
  python sim/isaac/sllm/infer.py --adapter sim/isaac/sllm/adapter \
      --demo sim/dataset/tactile_pills.npz
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_corpus import INSTRUCTION, make_record, _fmt_input


def load(model_id, adapter):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel
    tok = AutoTokenizer.from_pretrained(adapter if os.path.isdir(adapter) else model_id)
    dtype = torch.bfloat16 if torch.cuda.is_available() else torch.float32
    base = AutoModelForCausalLM.from_pretrained(model_id, torch_dtype=dtype)
    model = PeftModel.from_pretrained(base, adapter) if os.path.isdir(adapter) else base
    model.eval()
    if torch.cuda.is_available():
        model = model.cuda()
    return model, tok


def generate(model, tok, record_text, max_new=160):
    import torch
    msgs = [{"role": "system", "content": INSTRUCTION},
            {"role": "user", "content": record_text}]
    prompt = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    ids = tok(prompt, return_tensors="pt").to(model.device)
    t0 = __import__("time").time()
    with torch.no_grad():
        out = model.generate(**ids, max_new_tokens=max_new, do_sample=False,
                             pad_token_id=tok.pad_token_id or tok.eos_token_id)
    dt = __import__("time").time() - t0
    gen = out[0, ids["input_ids"].shape[1]:]
    return tok.decode(gen, skip_special_tokens=True).strip(), dt, len(gen)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="Qwen/Qwen2.5-0.5B-Instruct")
    ap.add_argument("--adapter", default="sim/isaac/sllm/adapter")
    ap.add_argument("--demo", default=None, help="npz dataset to sample trays from")
    ap.add_argument("--trays", type=int, default=3)
    a = ap.parse_args()

    model, tok = load(a.model, a.adapter)

    if a.demo:
        d = np.load(a.demo)
        press = d["pill_pressure"].astype(float); lab = d["pill_label"].astype(int)
        mu = press[lab == 0].mean(); sigma = press[lab == 0].std()
        rng = np.random.default_rng(0)
        # show a mix: some trays with voids, some clean
        void_trays = np.where(lab.sum(1) > 0)[0]
        clean_trays = np.where(lab.sum(1) == 0)[0]
        pick = list(rng.choice(void_trays, min(a.trays - 1, len(void_trays)), replace=False))
        if len(clean_trays):
            pick.append(int(rng.choice(clean_trays)))
        for t in pick:
            rec = make_record(press[t], lab[t], mu, sigma, tray_id=int(t))
            txt = _fmt_input(rec)
            report, dt, ntok = generate(model, tok, txt)
            print("=" * 70)
            print(txt)
            print("-- QC sLLM report --")
            print(report)
            print(f"[{ntok} tok in {dt*1000:.0f} ms = {ntok/max(dt,1e-6):.1f} tok/s]")
    else:
        print("provide --demo <npz> to sample inspection records")


if __name__ == "__main__":
    main()
