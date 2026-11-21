"""Train on reviewed JSONL rows: {run: <saved replay>, review: <human label>}."""
import argparse
import json
from protocol import messages, validate_review


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--model', required=True)
    p.add_argument('--data', required=True)
    p.add_argument('--output', default='adapters/cube-coach')
    p.add_argument('--epochs', type=int, default=3)
    p.add_argument('--context', type=int, default=4096)
    p.add_argument('--max-steps', type=int, default=-1, help='Limit training for a smoke check')
    args = p.parse_args()
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, Trainer, TrainingArguments
    from peft import LoraConfig, get_peft_model
    tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=True)
    tokenizer.pad_token = tokenizer.eos_token
    base = AutoModelForCausalLM.from_pretrained(args.model, local_files_only=True, torch_dtype=torch.float32)
    model = get_peft_model(base, LoraConfig(task_type='CAUSAL_LM', r=8,
        lora_alpha=16, lora_dropout=0.05, target_modules=['q_proj', 'v_proj']))
    rows = []
    with open(args.data, encoding='utf-8-sig') as f:
        for line in f:
            row = json.loads(line)
            review = validate_review(row['review'])
            chat = messages(row['run'])
            prefix = tokenizer.apply_chat_template(chat, tokenize=True, add_generation_prompt=True)
            chat.append({'role':'assistant','content':json.dumps(review, separators=(',',':'))})
            ids = tokenizer.apply_chat_template(chat, tokenize=True, add_generation_prompt=False)
            if len(ids) > args.context:
                raise ValueError('Training replay exceeds context; do not truncate inputs silently')
            if ids[:len(prefix)] != prefix:
                raise ValueError('Chat template prefix mismatch: choose a compatible instruct tokenizer')
            rows.append({'input_ids':ids, 'attention_mask':[1]*len(ids),
                         'labels':[-100]*len(prefix)+ids[len(prefix):]})
    if not rows:
        raise ValueError('No training examples. Human-reviewed gameplay labels are required.')
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

if __name__ == '__main__':
    main()
