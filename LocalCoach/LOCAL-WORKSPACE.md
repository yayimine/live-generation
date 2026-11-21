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

## Desktop app

Double-click **Cube Coach Studio.app** in the Unity project folder. Keep the app next to `LocalCoach`.

- **Import replays** selects the Unity Runs folder. **Refresh** reloads imported data.
- Select a run to inspect its recorded positions, goal layout, and full JSON.
- Enter a rating, feedback, proposed level, split, and session group, then **Save label**.
- **Export datasets** validates the saved labels and produces train/test JSONL.
- **Train new adapter** exports labels first and starts training into a new timestamped folder. Training output appears at the bottom.
- **Start coach** can use the base model or an adapter folder you choose. **Stop job** ends a job started by Studio.

Studio runs one training or coach job at a time. Stop a separately launched coach before starting another on the same port. A route preview joins positions captured at input changes, so use the full replay JSON when judging timing or boundary contacts. The project-local model and ML environment are required for training and inference. The app includes its own GUI runtime. To rebuild the app, run `.venv/bin/python build_studio.py` from `LocalCoach` with PyInstaller installed.

### Collect runs inside Studio

Click **Play & collect…**, then **Start practice**. Move with WASD and collect the
yellow goals and steer around the solid gray blocks. Practice goals and blocks
are randomized each run. Coach layouts use the coach’s goal coordinates and
receive randomized blocks. A run saves automatically when you collect all goals, the clock
expires, or you press Enter. The saved run appears immediately in Studio and uses
the same replay fields as imported Unity runs. Select it, save a label, then
export or train with any mix of Studio and imported Unity runs.

To collect runs on adapted layouts, first use **Start coach…** in Studio to load
the base model or a trained adapter. After a run, click **Ask coach** and then
**Play generated level** when a valid layout arrives. Coach feedback is displayed
separately from the human label you save for training.
