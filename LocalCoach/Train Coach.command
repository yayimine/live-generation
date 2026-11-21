#!/bin/zsh
cd -- "${0:A:h}" || exit 1
.venv/bin/python workspace.py export || exit 1
if [[ -d adapters/cube-coach ]]; then
  print "Move adapters/cube-coach aside before starting a fresh training run."
else
  .venv/bin/python train_lora.py --model models/qwen2.5-0.5b-instruct --data data/train.jsonl --output adapters/cube-coach --context 4096
fi
read "?Press Enter to close."
