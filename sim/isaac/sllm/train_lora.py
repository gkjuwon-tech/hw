"""LoRA fine-tune a small LLM into the Conet Tactile on-device QC reporter.

Takes the base sLLM (default Qwen2.5-0.5B-Instruct — a size that runs in real
time on the Jetson Orin Nano once INT4-quantized) and LoRA-fine-tunes it on the
synthetic QC-report corpus so it speaks our inspection domain: tactile pressure
deficits, internal-void physics, reject/divert actions.

We train completion-only (the prompt tokens are masked; loss is on the report)
so the adapter learns to *write the report*, not to echo the record. LoRA keeps
the trainable footprint tiny and the merged model is exported for the edge in
`export_edge.py`.

Run (env with torch+transformers+peft):
  python sim/isaac/sllm/train_lora.py --corpus sim/isaac/sllm/corpus.jsonl \
      --model Qwen/Qwen2.5-0.5B-Instruct --out sim/isaac/sllm/adapter --epochs 3
"""
from __future__ import annotations

import argparse
import json
import os


def load_pairs(path):
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="sim/isaac/sllm/corpus.jsonl")
    ap.add_argument("--model", default="Qwen/Qwen2.5-0.5B-Instruct")
    ap.add_argument("--out", default="sim/isaac/sllm/adapter")
    ap.add_argument("--epochs", type=float, default=3.0)
    ap.add_argument("--bs", type=int, default=8)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--maxlen", type=int, default=512)
    ap.add_argument("--val", type=int, default=200, help="held-out examples")
    a = ap.parse_args()

    import torch
    from transformers import (AutoModelForCausalLM, AutoTokenizer,
                              Trainer, TrainingArguments)
    from peft import LoraConfig, get_peft_model

    tok = AutoTokenizer.from_pretrained(a.model)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token

    rows = load_pairs(a.corpus)
    val_rows, train_rows = rows[:a.val], rows[a.val:]
    print(f"[lora] {len(train_rows)} train / {len(val_rows)} val examples")

    def encode(ex):
        """Build prompt+response ids with the prompt masked out of the loss."""
        prompt_msgs = [{"role": "system", "content": ex["instruction"]},
                       {"role": "user", "content": ex["input"]}]
        prompt = tok.apply_chat_template(prompt_msgs, tokenize=False,
                                         add_generation_prompt=True)
        full = prompt + ex["output"] + tok.eos_token
        pid = tok(prompt, add_special_tokens=False)["input_ids"]
        fid = tok(full, add_special_tokens=False)["input_ids"][:a.maxlen]
        labels = list(fid)
        for i in range(min(len(pid), len(labels))):
            labels[i] = -100
        return {"input_ids": fid, "labels": labels, "attention_mask": [1] * len(fid)}

    train_ds = [encode(r) for r in train_rows]
    val_ds = [encode(r) for r in val_rows]

    def collate(batch):
        m = max(len(b["input_ids"]) for b in batch)
        pad = tok.pad_token_id
        out = {"input_ids": [], "attention_mask": [], "labels": []}
        for b in batch:
            k = m - len(b["input_ids"])
            out["input_ids"].append(b["input_ids"] + [pad] * k)
            out["attention_mask"].append(b["attention_mask"] + [0] * k)
            out["labels"].append(b["labels"] + [-100] * k)
        return {k: torch.tensor(v) for k, v in out.items()}

    dtype = torch.bfloat16 if torch.cuda.is_available() else torch.float32
    model = AutoModelForCausalLM.from_pretrained(a.model, torch_dtype=dtype)
    model.config.use_cache = False
    lora = LoraConfig(r=16, lora_alpha=32, lora_dropout=0.05, bias="none",
                      task_type="CAUSAL_LM",
                      target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                                      "gate_proj", "up_proj", "down_proj"])
    model = get_peft_model(model, lora)
    model.print_trainable_parameters()

    args = TrainingArguments(
        output_dir=a.out + "_ckpt", per_device_train_batch_size=a.bs,
        gradient_accumulation_steps=2, num_train_epochs=a.epochs,
        learning_rate=a.lr, lr_scheduler_type="cosine", warmup_ratio=0.03,
        logging_steps=25, eval_strategy="epoch", save_strategy="no",
        bf16=torch.cuda.is_available(), report_to=[], remove_unused_columns=False)
    trainer = Trainer(model=model, args=args, train_dataset=train_ds,
                      eval_dataset=val_ds, data_collator=collate)
    trainer.train()

    os.makedirs(a.out, exist_ok=True)
    model.save_pretrained(a.out)
    tok.save_pretrained(a.out)
    print(f"[lora] saved adapter -> {a.out}")


if __name__ == "__main__":
    main()
