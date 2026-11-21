# Collect gameplay and train Cube Coach on Windows

This tutorial uses PowerShell, Unity 6000.3.16f1, and Python 3.12 on an x64 Windows PC. The first pass trains a LoRA adapter for Qwen2.5-0.5B-Instruct using actual Cube Coach replays and human-written feedback. The base weights stay the same. Keep the base model directory with the adapter so you can run the coach locally after training. [Qwen model card](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct) · [PEFT LoRA guide](https://huggingface.co/docs/peft/main/en/conceptual_guides/lora)

## 1. Plan the collection

| Stage | Target | Purpose |
| --- | --- | --- |
| Pilot | 12–20 runs, including at least 8 for training and 4 held out | Check capture, labels, training, and inference before collecting more |
| First dataset | 150–300 distinct runs, ideally across several players and sessions | Cover different routes, skill levels, and outcomes |
| Evaluation | About 20% held out, including a final set you keep untouched while tuning | Compare the base model and adapter on the same unfamiliar replays |

Treat these counts as starting points. Collect quick and slow clears, partial clears, timeouts, and early finishes. Include direct routes, backtracking, idle periods, and runs that hit arena boundaries. Record the actual session for each replay in your own notes. Keep all runs from one player in the same split where possible. If you're the only player, split by session. Keep repeated versions of a run together.

Start with the practice arena. Once the base coach is running, you can play valid generated arenas to collect different layouts, then write the target reviews yourself. Include some unfamiliar layouts in evaluation and compare results on familiar and unfamiliar layouts separately. Ask playtesters before collecting their runs and use session IDs in your notes.

## 2. Collect real Unity replays

1. In Unity Hub, open the project folder containing `Assets`, `ProjectSettings`, and `LocalCoach`. Open `Assets/Scenes/SampleScene.unity` and press **Play**.
2. Move with WASD. Collect all yellow goals, let the clock expire, or press **Enter** to finish. The game writes the replay before contacting the coach, so you can collect data before setting up inference. Choose **Replay practice** to start again.
3. In the Unity Console, look for **Cube Coach replay** and open the printed folder. With the current project settings, you can also open the default folder with this PowerShell command. [Unity persistent data paths](https://docs.unity.com/en-us/engine/6000.0/script-reference/unityengine/application/persistentdatapath)

```powershell
explorer.exe "$env:USERPROFILE\AppData\LocalLow\DefaultCompany\live generation\Runs"
```

Each replay has the original level, timed input changes, goal hits, total duration, distance, and completion status. Goal indices in `hits` start at zero. `inputs` contains state changes rather than one record per frame. A mask persists until the next event or the end of the run. W = 1, A = 2, S = 4, and D = 8. For example, 9 is W+D and 0 is idle. Keep the complete replay. When copying files, use the run ID files and skip any `*.review.json` model outputs.

## 3. Set up Python and download the base model

Install [Python 3.12 for Windows](https://www.python.org/downloads/windows/) and open PowerShell in the project folder. The commands below call the virtual environment's Python directly.

```powershell
Set-Location .\LocalCoach
py -3.12 -m venv .venv
$Py = (Resolve-Path .\.venv\Scripts\python.exe).Path
& $Py -m pip install --upgrade pip
```

**NVIDIA GPU.** Use the PyTorch selector for **Windows**, **Pip**, **Python**, and a CUDA version supported by your driver. In the generated command, replace the leading `pip` or `pip3` with `& $Py -m pip`. Install PyTorch before the project requirements so the environment uses your chosen wheel. [PyTorch installation selector](https://pytorch.org/get-started/locally/)

**CPU pilot.** If you don't have a supported NVIDIA GPU, use this CPU wheel command. Start with a few short replays. Full training on CPU can be slow.

```powershell
& $Py -m pip install "torch>=2.6,<3" --index-url https://download.pytorch.org/whl/cpu
```

Continue with either setup.

```powershell
& $Py -m pip install -r requirements.txt
& $Py -c "import torch; print(torch.__version__); print('CUDA:', torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')"
& .\.venv\Scripts\hf.exe download Qwen/Qwen2.5-0.5B-Instruct --local-dir .\models\qwen2.5-0.5b-instruct
& $Py -m pip freeze | Set-Content -Encoding ascii .\training-environment.txt
```

If the GPU check prints `CUDA: False` on an NVIDIA setup, check `nvidia-smi` and the PyTorch wheel before starting training. Keep the downloaded model directory unchanged for comparisons and adapter use. For a repeatable download, record the model commit from its model page and pass it to `hf download --revision <commit>`. The download needs internet access. Training and inference use the resulting local files. [Hugging Face CLI](https://huggingface.co/docs/huggingface_hub/en/guides/cli)

## 4. Label and split the runs

Create folders under `LocalCoach` and copy each replay to the appropriate split. Use fresh folders or keep pilot files separate from your full dataset.

```powershell
New-Item -ItemType Directory -Force .\data\train, .\data\test | Out-Null
```

For each `<id>.json` replay, save a UTF-8 file named `<id>.label.json` next to it. In Notepad, choose **All files** when saving so the filename ends in `.json`. Use one rubric across the dataset.

| Component | Points | How to judge it |
| --- | --- | --- |
| Goals | 0–6 | Multiply the fraction of goals hit by 6 and round to the nearest integer, rounding halves up |
| Route | 0–2 | Give 0 for no purposeful progress or repeated major detours, 1 for some backtracking, and 2 for a direct route given the goals reached |
| Time | 0–2 | Give 2 for clearing within half the time limit, 1 for clearing later, and 0 for an incomplete run |

Add the points and use a minimum rating of 1. Give one specific observation grounded in the run and one action the player can try. Match the next level to the observed skill. For instance, an incomplete run with backtracking can get fewer goals in a clear route, while a clean clear can get a wider layout or tighter time budget. Vary the proposed layouts within each rating band.

Example label for a run that cleared all goals late and took several major detours (6 + 0 + 1):

```json
{
  "rating": 7,
  "feedback": "You cleared every goal but crossed the middle several times. Try picking a clockwise order before moving.",
  "nextLevel": {
    "title": "Wide sweep",
    "description": "Collect the two yellow cubes on opposite sides of the arena.",
    "seconds": 35,
    "goals": [{"x": -5, "y": 3}, {"x": 5, "y": -3}]
  }
}
```

Use 1–8 goals, with x between −8 and 8 and y between −4 and 4. Each goal must be at least 1.3 units from spawn and 1.4 units from every other goal. Use 15–90 seconds. Check that the intended route fits the time budget at 4.5 units per second with room for turns. Have a second reviewer score a few runs independently if available, then agree on how to handle borderline cases.

## 5. Build the training files

Paste the whole block below into PowerShell from `LocalCoach`. It pairs replays with labels, checks the review schema, rejects repeated run IDs across both splits, and writes one complete `{"run":...,"review":...}` JSON object per line.

```powershell
@'
import json
from pathlib import Path
from protocol import validate_review

datasets = {}
seen = set()
for split in ("train", "test"):
    rows = []
    for path in sorted((Path("data") / split).glob("*.json")):
        if path.name.endswith((".label.json", ".review.json")):
            continue
        label = path.with_suffix(".label.json")
        try:
            run = json.loads(path.read_text(encoding="utf-8-sig"))
            run_id = run["id"]
            if run_id in seen:
                raise ValueError(f"duplicate run ID {run_id}")
            for key in ("level", "inputs", "hits", "duration", "completed"):
                if key not in run:
                    raise ValueError(f"replay is missing {key}")
            review = validate_review(json.loads(label.read_text(encoding="utf-8-sig")))
            rows.append(json.dumps({"run": run, "review": review}, allow_nan=False))
            seen.add(run_id)
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
            raise SystemExit(f"{path}: {error}") from error
    if not rows:
        raise SystemExit(f"data/{split} contains no labeled replays")
    datasets[split] = rows

for split, rows in datasets.items():
    Path(f"data/{split}.jsonl").write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(f"{split}: {len(rows)} labeled runs")
'@ | & $Py -
```

## 6. Train the adapter

Run the pilot using a small labeled training split. The script uses batch size one, accumulates gradients across eight examples, and trains only LoRA weights on the attention layers. The targets are the human-written reviews.

```powershell
$Model = ".\models\qwen2.5-0.5b-instruct"
& $Py .\train_lora.py --model $Model --data .\data\train.jsonl --output .\adapters\pilot --epochs 1 --context 4096
Get-ChildItem .\adapters\pilot\adapter*
```

Look for `adapter_config.json` and `adapter_model.safetensors`. After the pilot works, expand the labeled dataset, rebuild the JSONL files, and train a fresh adapter from the same base.

```powershell
& $Py .\train_lora.py --model $Model --data .\data\train.jsonl --output .\adapters\cube-coach-v1 --epochs 3 --context 4096
```

If a replay exceeds the context, keep the original intact and either raise `--context` within the model and device limits or separate that replay from this training batch. If CUDA runs out of memory, close other GPU workloads and pilot on short runs with a smaller context. Batch size is already one. A falling training loss is a diagnostic. Use held-out reviews to judge quality.

## 7. Compare the base model and adapter

Open a second PowerShell window in `LocalCoach`. Start the base model in the first window.

```powershell
& $Py .\server.py --model $Model
```

In the second window, run the following on the held-out set. Give slow CPU inference time to finish. Use the same script for both models.

```powershell
$Py = (Resolve-Path .\.venv\Scripts\python.exe).Path
$Report = "data/base-results.jsonl"
Invoke-RestMethod http://127.0.0.1:8765/health

@'
import json
from pathlib import Path
import sys
import urllib.error
import urllib.request

with Path(sys.argv[1]).open("w", encoding="utf-8") as output:
    for line in Path("data/test.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        run = row["run"]
        request = urllib.request.Request(
            "http://127.0.0.1:8765/review",
            data=json.dumps(run).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                result = json.load(response)
        except (urllib.error.URLError, TimeoutError) as error:
            detail = error.read().decode("utf-8") if isinstance(error, urllib.error.HTTPError) else str(error)
            result = {"error": detail}
        record = {"id": run["id"], "expected": row["review"], "actual": result}
        output.write(json.dumps(record) + "\n")
        print(run["id"], result.get("rating", result.get("error")))
'@ | & $Py - $Report
```

Stop the base server with **Ctrl+C**. In the first window, start the adapter server. Use `.\adapters\pilot` if you only trained the pilot.

```powershell
& $Py .\server.py --model $Model --adapter .\adapters\cube-coach-v1
```

In the evaluation window, rerun the block with `$Report = "data/adapter-results.jsonl"`. For each model, count valid replies out of all held-out runs and calculate average absolute rating error on valid replies. Also count how often a run got a valid rating within one point of its human rating, using all runs as the denominator. Read the feedback and mark claims the replay doesn't support. Play a sample of levels from incomplete and clean runs to check whether the description, difficulty, and time limit make sense. More than one layout can be a good answer. Prefer the adapter if it makes ratings or feedback better while preserving the rate of usable levels. Keep the final test set for the chosen version.

## 8. Test in Unity and save the result

With the adapter server running, finish a fresh Unity run and wait for the review. If Unity says insecure connections are blocked, use **Edit → Project Settings → Player → Other Settings → Configuration → Allow downloads over HTTP → Allowed in Development Builds** on your development copy. This setting lets the Unity Editor contact the local HTTP endpoint. [Unity HTTP setting](https://docs.unity.com/en-us/engine/6000.0/script-reference/unityeditor/playersettings/insecurehttpoption)

Check that the rating and next-level description appear. Click **Play generated level**, confirm the number and positions of goals, then finish that level and check the second review. The saved `*.review.json` should identify the source as `local LoRA model`. Keep the adapter files, base model revision, dependency snapshot, and evaluation results together. The Windows workflow uses a separate local coach process. The project's existing automatic app bundling targets Apple Silicon macOS.
