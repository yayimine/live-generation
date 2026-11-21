# Cube / Coach

Unity 6000.3.16f1 top-down prototype. Open `Assets/Scenes/SampleScene.unity`
and press **Play**. The runtime bootstrap creates the arena automatically.
WASD moves the cyan player cube; touch all yellow goal cubes. Enter ends a run
early. A run also ends after its time limit. Click **Play generated level**
after the local coach returns its rating, feedback, description, and goal layout.
Each practice run places four goals at random. Every arena also places three
to five solid gray blocks, with clearance around the spawn and goals.

## Game code

`CubeCoach` coordinates the play, review, and results phases. `RunSession`
handles movement, goal contacts, and replay events. `ArenaRules` owns arena
dimensions, the practice layout, and generated level validation. `ArenaView`
renders the arena, and `CoachHud` displays the run and returns player actions.
`ReplayData` defines the JSON fields and `ReplayStore` writes files. `HttpCoach`
and `BundledCoach` handle the two local inference connections.

## Local inference

The Unity game talks only to `http://127.0.0.1:8765/review`. The Python process
runs on the same computer; this is a desktop prototype, not a bundled mobile runtime.
No gameplay is uploaded. Base weights and a trained LoRA adapter are not included.
Without the server the game still plays and saves replays; it shows an explicit
connection error and offers retry or practice. It never substitutes fake AI scores.

Use Python 3.11 or 3.12 with a supported PyTorch build:

```sh
cd LocalCoach
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python server.py --model /absolute/path/to/local-instruct-model --adapter /absolute/path/to/cube-coach-adapter
```

Choose a small Transformers-compatible instruct model with a chat template and
q_proj/v_proj attention layers (for example Qwen2.5-0.5B-Instruct). Download its
weights separately from its official model repository, review its license, then
pass its local directory. Inference uses offline loading, CUDA or Apple MPS where
available, and CPU otherwise. No download occurs in the server. To test the
integration before training, omit `--adapter`; the UI explicitly identifies the
base model. LoRA fine-tunes behavior; it does not quantize the base model.

## Train a LoRA adapter

Replays are JSON in `Application.persistentDataPath/Runs`; Unity logs the
persistent data path through its standard API. Each run includes its original
level, every observed WASD bitmask change with time and position, all goal hits,
duration, distance, final position, and completion. Masks: W=1 A=2 S=4 D=8.
These are movement inputs observed each rendered frame, not an OS-wide keylogger.
Held states are encoded by transitions, with duration defining the last interval.
The game clock caps long-frame movement steps at 50ms.

Create a JSONL dataset, one row per run, containing `run` (the saved JSON object)
and `review` (a human-reviewed target). Review format:

```json
{"rating":7,"feedback":"Try planning the return route before moving.","nextLevel":{"title":"Wide sweep","description":"Collect two yellow cubes on opposite sides of the arena.","seconds":35,"goals":[{"x":-5,"y":3},{"x":5,"y":-3}]}}
```

```sh
python train_lora.py --model /path/to/base --data reviewed-runs.jsonl --output adapters/cube-coach
python server.py --model /path/to/base --adapter adapters/cube-coach
```

Training masks prompt tokens, trains rank-8 LoRA attention adapters, and saves
only adapter weights. Use the identical base model for training and serving.
Collect varied, carefully rated examples and evaluate held-out runs before
claiming improved coaching. Automatic self-labeling is not training evidence.
No model or adapter has been trained or benchmarked as part of this prototype.

All input events are sent to the model; oversized contexts are rejected rather
than silently truncated. Generation is capped at 650 new tokens. Invalid JSON,
out-of-bounds, overlapping, or spawn-adjacent goals are rejected with a retry
option. The game places isolated blocks after validating the goal coordinates and records
the block centers with the replay. Older replays may omit obstacles.
Slow CPU inference may exceed Unity's 180-second request timeout.

## Checks

```sh
cd LocalCoach
python -m unittest discover -s tests -v
python -m py_compile protocol.py server.py train_lora.py
```

Manual check: move diagonally and against boundaries, collect a goal, finish via
Enter, inspect the replay, start the local server, retry the review, then launch
the generated level. Also test server unavailable and invalid model output.

Implementation references: [PEFT LoRA](https://huggingface.co/docs/peft/quicktour)
and [Transformers generation](https://huggingface.co/docs/transformers/main_classes/text_generation).

## Bundle the coach into an Apple Silicon macOS build

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) on the
build machine. Prepare the bundle from the project directory using the same
local base weights and trained PEFT adapter as above.

```sh
python3 LocalCoach/prepare_macos_bundle.py --model /path/to/base --adapter /path/to/adapter
```

The script stages a portable Python interpreter, inference dependencies, the
base weights, and adapter in `LocalCoach/macos-runtime`. It checks that the
model and adapter load after moving the runtime. Select **macOS** and **Apple
Silicon** in Unity Build Profiles and build normally. Unity copies the staged
runtime into the app and applies an ad hoc signature for local testing. Each
build uses the currently staged files. Move the staging directory aside and
rerun the preparation command to update them.

Open the resulting app to play. It loads the bundled model in the background,
communicates with it through process pipes, and stops it when the game exits.
Players need no separate Python installation, terminal, or network connection.
The app grows by the size of the model and runtime. Developer ID signing and
notarization for public distribution are separate from this local build flow.

For the Windows data collection and LoRA workflow, see
[Collect gameplay and train Cube Coach on Windows](WINDOWS-TRAINING.md).

For the installed local model, collection commands, and training launchers, see
[Local workspace](LocalCoach/LOCAL-WORKSPACE.md).
