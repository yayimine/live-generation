# Cube Coach device transfer and rebuild

This guide restores the current Cube Coach Unity project on another desktop. It covers the source transfer, Unity setup, local model, LoRA training, and platform builds. Keep this Markdown file with the source. You also need the actual project files.

## 1. Copy the project from the original device

1. Save your scenes and close Unity so the copied files represent a consistent snapshot.
2. Find the **inner** `live generation` folder. It is the one containing `Assets`, `Packages`, and `ProjectSettings`. Copy the following from that folder into a single folder on the destination device.

   | Copy | Why |
   | --- | --- |
   | `Assets/` with all `.meta` files | Scenes, scripts, input actions, and the URP settings and asset references |
   | `Packages/` | `Packages/manifest.json` and `Packages/packages-lock.json` |
   | `ProjectSettings/` | Unity version, build scene list, graphics, input, and player settings |
   | `LocalCoach/` Python sources, `requirements.txt`, and `tests/` | Model server, training, validation, and macOS preparation code |
   | `CUBE-COACH-HANDOFF.md`, `README-CubeCoach.md`, and `WINDOWS-TRAINING.md` | Setup instructions and the full Windows labeling and evaluation tutorial |
   | `.gitignore` and `LocalCoach/.gitignore` | Ignore rules if you continue using Git |

3. Use a ZIP, a USB drive, or your normal private file transfer method. A fresh Git clone or `git archive` will miss local edits and untracked files unless those files have been committed and transferred. This snapshot has local changes, including game and coach files. Copy the working folder items directly to capture them. Copy `.git/` too if you need local branches and history.
4. Leave out generated directories such as `Library/`, `Temp/`, `Obj/`, `Logs/`, and `UserSettings/`, along with generated solution files and Python caches. Unity rebuilds its import cache. Recreate `LocalCoach/.venv/` on the destination OS. Prepare the macOS runtime again when needed.

### Preserve training and model files separately

If you collected gameplay, retain the raw `Runs/` files, human labels, train/test JSONL splits, and evaluation results. The replay folder is outside the project. Finish a run and find the **Cube Coach replay** path in the Unity Console to locate it. On Windows the default folder is `%USERPROFILE%\AppData\LocalLow\DefaultCompany\live generation\Runs`. Copy it to the equivalent persistent data folder to preserve local history, or keep it in a labeled dataset backup.

If you downloaded a base model, copy its full Transformers directory, including tokenizer files, configuration, and all weights. If you trained an adapter, copy the full adapter directory, including `adapter_config.json` and `adapter_model.safetensors`. Record the exact base model revision and keep any dependency snapshot. These files can be ignored by Git. The source snapshot inspected for this guide had no base model, labeled dataset, trained adapter, or staged macOS runtime.

## 2. Open the game on the destination

1. Install Unity Hub and Unity Editor **6000.3.16f1**, the version in `ProjectSettings/ProjectVersion.txt`. Use the Editor and build support for the platform you plan to build for.
2. In Unity Hub, add the copied project folder. Wait for the package restore and asset import to finish.
3. Open `Assets/Scenes/SampleScene.unity`. Press **Play** and click the Game view. Check WASD movement, collect a yellow goal, then press **Enter** to finish early. The Console should print a replay path. The scene bootstrap creates the arena at runtime.
4. **Replay practice** lets you repeat the test before the model is set up. A coach connection error at this point is expected. Replay files should still be saved.

## 3. Set up Python and the base model

Run these commands from the copied project root. Use Python 3.12 on the destination.

### Windows PowerShell

```powershell
Set-Location .\LocalCoach
py -3.12 -m venv .venv
$Py = (Resolve-Path .\.venv\Scripts\python.exe).Path
& $Py -m pip install --upgrade pip
```

For NVIDIA acceleration, install a Windows CUDA wheel from the [PyTorch installation selector](https://pytorch.org/get-started/locally/) before installing the requirements. Use `& $Py -m pip` as the command prefix. For a CPU setup, run:

```powershell
& $Py -m pip install "torch>=2.6,<3" --index-url https://download.pytorch.org/whl/cpu
```

Then run:

```powershell
& $Py -m pip install -r requirements.txt
& $Py -m unittest discover -s tests -v
```

### macOS Terminal

```sh
cd LocalCoach
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
```

### Restore model files

Put the copied base directory at `LocalCoach/models/qwen2.5-0.5b-instruct` if using Qwen, or substitute your actual model path in later commands. If you have an adapter, use the exact base revision it was trained against. For a fresh base model, download [Qwen2.5-0.5B-Instruct](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct) from the installed Hugging Face CLI:

```powershell
& .\.venv\Scripts\hf.exe download Qwen/Qwen2.5-0.5B-Instruct --local-dir .\models\qwen2.5-0.5b-instruct
```

```sh
.venv/bin/hf download Qwen/Qwen2.5-0.5B-Instruct --local-dir models/qwen2.5-0.5b-instruct
```

If replicating an earlier setup, add `--revision` with the recorded model commit. Package installation and fresh model downloads require internet. The coach loads the model from disk and processes replays locally.

## 4. Run the coach and play a generated level

From `LocalCoach`, start the server with the copied adapter if you have one:

```powershell
& $Py .\server.py --model .\models\qwen2.5-0.5b-instruct --adapter .\adapters\cube-coach
```

```sh
.venv/bin/python server.py --model models/qwen2.5-0.5b-instruct --adapter adapters/cube-coach
```

If you have no trained adapter yet, omit `--adapter` and its path to test the base model. Keep the server terminal open. Once it prints **Coach ready**, check `http://127.0.0.1:8765/health` in a browser. It should report the model source and device.

Finish a Unity run. If the Editor blocks the loopback HTTP request, set **Edit → Project Settings → Player → Other Settings → Configuration → Allow downloads over HTTP** to **Allowed in Development Builds** on the development copy, then retry. Unity should display a score and next-level description once the model returns a valid response. Click **Play generated level** and finish it to check the second run. A successful review is written next to the replay as `<run-id>.review.json`. If a base-model response is invalid, check the returned error and try another replay. Schema validation can reject model output.

## 5. Train or restore LoRA

A copied compatible adapter can go straight into Step 4. To build one from scratch, follow [WINDOWS-TRAINING.md](WINDOWS-TRAINING.md) for the scoring rubric, dataset conversion, and held-out evaluation. The same Python scripts run on macOS with `.venv/bin/python`.

1. Collect varied real runs in Unity. Start with a small pilot before scaling collection.
2. Pair each replay with a human-written review. Each JSONL line must be an object with `run` and `review`, where the review contains `rating`, `feedback`, and `nextLevel`. Split by player or session where possible and reserve test runs.
3. Build `data/train.jsonl` and `data/test.jsonl` using the conversion block in the Windows tutorial. Run training after the files validate.

```powershell
& $Py .\train_lora.py --model .\models\qwen2.5-0.5b-instruct --data .\data\train.jsonl --output .\adapters\cube-coach --epochs 3 --context 4096
```

```sh
.venv/bin/python train_lora.py --model models/qwen2.5-0.5b-instruct --data data/train.jsonl --output adapters/cube-coach --epochs 3 --context 4096
```

Compare the base model and adapter on the same held-out runs. Check rating accuracy, feedback against the replay, and whether generated levels play as described. Real model training and inference need to be verified on the destination machine.

## 6. Rebuild a standalone game

| Target | Build and launch |
| --- | --- |
| Windows | Select **Windows** in **File → Build Profiles**, keep `SampleScene` in the scene list, and build. For coach testing in the player, use **Development Build** with the development-only HTTP setting, and start the local Python server separately. Keep the executable and its companion files together. |
| Apple Silicon macOS, bundled coach | On an Apple Silicon Mac, install [uv](https://docs.astral.sh/uv/getting-started/installation/). From the project root run the staging command below. Select **macOS** and **Apple Silicon** in Build Profiles and build. The build hook copies the staged files into the app and applies a local ad hoc signature. |
| macOS development without a bundle | Run the local server as in Step 4 and use the Unity Editor to test the gameplay loop. |

```sh
python3.12 LocalCoach/prepare_macos_bundle.py \
  --model LocalCoach/models/qwen2.5-0.5b-instruct \
  --adapter LocalCoach/adapters/cube-coach
```

The staging command requires both sets of weights and checks that they load after relocating the runtime. The built macOS app starts its local coach through process pipes. Test a fresh run and replay generated goals with the separate server stopped. Windows builds use the separate server. The macOS copy and signing path has been tested with placeholder files. Verify a full build with your actual weights before relying on it.

## Source map

- `Assets/Scenes/SampleScene.unity` is the build scene.
- `Assets/Scripts/CubeCoach.cs` coordinates play, review, and results. `RunSession.cs` owns movement and replay events, `ArenaRules.cs` owns the practice and generated-level rules, and `ArenaView.cs` and `CoachHud.cs` render the game.
- `ReplayData.cs` defines the saved format, and `ReplayStore.cs` writes replay and review files. `HttpCoach.cs` and `BundledCoach.cs` connect to local inference.
- `LocalCoach/protocol.py` defines the model prompt and response validation. `server.py` runs inference, and `LocalCoach/train_lora.py` trains the adapter.
- `Assets/Editor/CubeCoachBundleBuild.cs` handles the macOS build copy and signing.

Before retiring the old copy, confirm the destination opens the scene, saves a fresh replay, has the training files you intend to keep, and can complete the full review and generated-level loop with your chosen model.
