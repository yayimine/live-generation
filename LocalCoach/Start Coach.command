#!/bin/zsh
cd -- "${0:A:h}" || exit 1
args=(--model models/qwen2.5-0.5b-instruct)
if [[ -f adapters/cube-coach/adapter_config.json ]]; then
  args+=(--adapter adapters/cube-coach)
fi
.venv/bin/python server.py "${args[@]}"
read "?Press Enter to close."
