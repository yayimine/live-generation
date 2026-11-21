"""Train on reviewed JSONL rows: {run: <saved replay>, review: <human label>}."""
import argparse
import json
from pathlib import Path
from protocol import messages, validate_rating, validate_review


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--model', required=True)
    p.add_argument('--data', required=True)
    p.add_argument('--output', default='adapters/cube-coach')
    p.add_argument('--epochs', type=int, default=3)
    p.add_argument('--context', type=int, default=4096)
    p.add_argument('--max-steps', type=int, default=-1, help='Limit training for a smoke check')
    args = p.parse_args()
    if args.context < 512:
        p.error("--context must be at least 512")
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, Trainer, TrainingArguments
    from peft import LoraConfig, get_peft_model
    tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=True)
    tokenizer.pad_token = tokenizer.eos_token
    rows = []
    with open(args.data, encoding='utf-8-sig') as f:
        examples = [json.loads(line) for line in f if line.strip()]
    rating_only = any("nextLevel" not in row["review"] for row in examples)
    response_budget = 48 if rating_only else 650
    condensed_count = 0
    for row in examples:
        run = row["run"]
        review = (validate_rating if rating_only else validate_review)(row["review"])
        target = {"role": "assistant", "content": json.dumps(review, separators=(",", ":"))}
        for condensed in (False, True):
            chat = messages(run, rating_only=rating_only, condensed=condensed)
            prefix = tokenizer.apply_chat_template(chat, tokenize=True, add_generation_prompt=True)
            if len(prefix) + response_budget > args.context:
                continue
            ids = tokenizer.apply_chat_template([*chat, target], tokenize=True, add_generation_prompt=False)
            if len(ids) <= args.context:
                break
        else:
            raise ValueError(f"Run {run.get('id', '(unknown)')} still exceeds the context after summarizing. "
                             "Increase Context and retry.")
        if condensed:
            condensed_count += 1
            print(f"Using input summary for {run.get('id', '(unknown)')} ({len(run['inputs'])} input events).",
                  flush=True)
        if ids[:len(prefix)] != prefix:
            raise ValueError("Chat template prefix mismatch: choose a compatible instruct tokenizer")
        rows.append({"input_ids": ids, "attention_mask": [1] * len(ids),
                     "labels": [-100] * len(prefix) + ids[len(prefix):]})
    if not rows:
        raise ValueError('No training examples. Human-reviewed gameplay labels are required.')
    print(f"Training on {len(rows)} runs: {len(rows) - condensed_count} full replays, "
          f"{condensed_count} input summaries.", flush=True)
    base = AutoModelForCausalLM.from_pretrained(args.model, local_files_only=True, torch_dtype=torch.float32)
    model = get_peft_model(base, LoraConfig(task_type='CAUSAL_LM', r=8,
        lora_alpha=16, lora_dropout=0.05, target_modules=['q_proj', 'v_proj']))
    # Batch size one avoids padding ambiguity and masks prompt tokens from loss.
    trainer = Trainer(model=model, train_dataset=rows, args=TrainingArguments(
        output_dir=args.output, per_device_train_batch_size=1, gradient_accumulation_steps=8,
        num_train_epochs=args.epochs, max_steps=args.max_steps,
        gradient_checkpointing=True, gradient_checkpointing_kwargs={"use_reentrant": False},
        learning_rate=2e-4, logging_steps=1,
        save_strategy='epoch', report_to='none', dataloader_pin_memory=False))
    trainer.train()
    model.save_pretrained(args.output)
    tokenizer.save_pretrained(args.output)
    (Path(args.output) / "coach_mode.json").write_text(
        json.dumps({"rating_only": rating_only, "run_summary": True, "condense_context": args.context}), encoding="utf-8")

if __name__ == '__main__':
    main()
