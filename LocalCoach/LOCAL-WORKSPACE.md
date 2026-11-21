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

The command displays the replay and asks for a whole-number rating from 1 to 10.
The split defaults to training. A session group is optional. When provided,
keep the same group in one split. Use the rubric in `../WINDOWS-TRAINING.md`.

4. Rate at least one training run, then export. Hold out test runs to evaluate quality.

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
- Enter a rating from 1 to 10, then **Save label**. The split defaults to training and the session group is optional.
- **Export datasets** validates the saved labels and produces train/test JSONL.
- **Train new adapter** exports labels first and starts training into a new timestamped folder. Training output appears at the bottom.
- **Start coach** loads the recovered adapter by default. Use **Coach options** to choose another adapter or the base model. **Stop job** ends a job started by Studio.

Studio runs one training or coach job at a time. Stop a separately launched coach before starting another on the same port. A route preview joins positions captured at input changes, so use the full replay JSON when judging timing or boundary contacts. The project-local model and ML environment are required for training and inference. The app includes its own GUI runtime. To rebuild the app, run `.venv/bin/python build_studio.py` from `LocalCoach` with PyInstaller installed.

### Collect runs inside Studio

Click **Play & collect…**, then **Start practice**. Move with WASD and collect the
yellow goals and steer around the solid gray blocks. Practice goals and blocks
are randomized each run. Coach layouts use the coach’s goal coordinates and
receive randomized blocks. A run saves automatically when you collect all goals, the clock
expires, or you press Enter. The saved run appears immediately in Studio and uses
the same replay fields as imported Unity runs. Select it, save a label, then
export or train with any mix of Studio and imported Unity runs.

To collect runs on adapted layouts, first use **Coach options** in Studio to load
the base model or an adapter that generates layouts. After a run, click **Ask coach** and then
**Play generated level** when a valid layout arrives. Coach feedback is displayed
separately from the human label you save for training.

Adapters trained with rating-only labels return a score. Start the base coach to collect model-generated layouts.


### Label a batch

Click **Label next run** to start the queue. Set the split and optional session
group on an unlabeled run to reuse them for the batch. With the replay list
focused, press **1–9** or **0** for 10 to save and advance. **Space** skips the
run for this session. **Undo** restores the previous label or returns a newly
rated run to the queue. **Reset skipped runs** brings manually skipped runs back.

The review shows goals hit, time used, distance, and the route. Click the
suggested rating to fill it in, then adjust it or confirm with **Enter**. The
suggestion uses goal completion and time, with a default route point when the
player moved. **Skip near-duplicates** compares unlabeled runs against labeled
ones on the same layout. It uses goal order, outcome, time, distance, and
recorded positions. Turn it off to include those runs in the queue.

### Compare the coach with the rubric

Studio shows idle input time, distance traveled, and the length of a reference
route around obstacles through the centers of the goals you hit, in order.
For completed runs the rubric uses estimated route efficiency alongside
completion and time. Players can collect a goal before reaching its center and
move in eight directions, so the efficiency figure is an estimate. The
suggested rating remains editable.

For a fair comparison, rate runs from held-out sessions, put them in **test**,
and export. Click **Evaluate ratings…** and choose the base model or an adapter.
The report in `data/evaluations` contains the rubric and model scores against
human labels, response times, valid reply count, and rating errors on matching
runs. Studio rejects matching train/test run IDs in the current exports.
Choose an adapter that has never trained on the test runs.

New adapters train with the run summary and receive it at inference. Earlier
adapters keep their original prompt. Retrain on your labeled runs to use
the summary with a LoRA adapter.
