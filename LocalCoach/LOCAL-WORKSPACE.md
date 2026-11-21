# Local collection and training workspace

This Mac has a project-local Python 3.12 environment at `.venv`. The selected base model is Qwen2.5-0.5B-Instruct. Its download revision is recorded in `model-source.json`, and installed packages are recorded in `training-environment.txt`. These files and weights stay on this device until you copy them.

## Collect and label

1. Open Unity, play SampleScene, and finish several runs. The Console prints the replay directory.
2. Double-click **Collect Runs.command**, or run the following from this folder.

```sh
.venv/bin/python workspace.py collect
.venv/bin/python workspace.py list
```

If Unity saved elsewhere, use `collect --source "/path/to/Runs"`. Import skips model review files and preserves each replay. You can import again after playing more runs.

3. Copy a run ID from the list and label that run.

```sh
.venv/bin/python workspace.py label RUN_ID
```

The command displays the replay, then asks for your rating, feedback, next-level description, timer, goal coordinates, train/test split, and player/session group. Use the rubric in `../WINDOWS-TRAINING.md`. Coordinates must be valid JSON. For example, `[{"x":-5,"y":3},{"x":5,"y":-3}]`. Keep the same player's or session's runs in one split. Export checks the group names for leakage.

4. Label both training and held-out runs, then export.

```sh
.venv/bin/python workspace.py export
```

Raw imported replays live in `data/runs`, labels in `data/labels`, and exported pairs in `data/train.jsonl` and `data/test.jsonl`. No gameplay labels are created automatically.

## Train and run

Stop the coach before training to free memory. Double-click **Train Coach.command** to export validated labels and train a fresh adapter at `adapters/cube-coach`. The launcher asks you to move an existing adapter aside before retraining. For a short first check, use:

```sh
.venv/bin/python train_lora.py --model models/qwen2.5-0.5b-instruct --data data/train.jsonl --output adapters/pilot --epochs 1 --max-steps 1
```

Double-click **Start Coach.command** to start inference. It selects `adapters/cube-coach` when present, otherwise it serves the base model. Return to Unity, finish a run, and request a review. The server prints its ready message after loading. The Unity development HTTP setting described in the Windows guide must allow the loopback request.

Compare held-out results before using a trained adapter as the default. See `../WINDOWS-TRAINING.md` for evaluation commands and collection targets. LoRA training uses your human labels. A successful technical training check establishes that the pipeline runs, and quality must be measured on real held-out gameplay.

The downloaded model and environment are excluded from Git. Use the preparation script documented in `../README-CubeCoach.md` if you want to bundle real weights and a trained adapter into a macOS build. For another device, copy source and data and recreate the Python environment for that OS.

## Verification on this device

The downloaded revision is recorded in `model-source.json`. Model inference ran on Apple MPS and returned a schema-valid rating and next-level layout for a synthetic replay. A single LoRA optimizer step completed and its saved adapter reloaded successfully. That disposable adapter is at `/private/tmp/cube-coach-smoke-adapter`; the launchers use the base model until you train `adapters/cube-coach` from real labels. Five protocol tests and a temporary replay-import/dataset-export check passed. The default Unity replay directory was empty or absent during setup. The project's development HTTP setting is enabled for the local server connection.
