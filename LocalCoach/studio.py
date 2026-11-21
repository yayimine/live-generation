"""Native desktop workspace for Unity replays and local LoRA training."""
import datetime
import json
from pathlib import Path
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from labeling import layout_and_outcome, near_duplicate, suggested_rating
from play_arena import OBSTACLE_SIZE, PlayArena
from protocol import validate_rating
from workspace import read
from run_metrics import baseline_rating, summarize
from studio_widgets import CopyText, fit_window, scroll_form, text_panel

ROOT = (Path(sys.executable).resolve().parents[3] / "LocalCoach"
        if getattr(sys, "frozen", False) else Path(__file__).resolve().parent)
PYTHON = ROOT / ".venv/bin/python"
DATA = ROOT / "data"
DEFAULT_ADAPTER = ROOT / "adapters" / "coach-20261120-230726-recovered"
DEFAULT_RUNS = Path.home() / "Library/Application Support/DefaultCompany/live generation/Runs"


class Studio:
    def __init__(self, window):
        self.window = window
        self.window.title("Cube Coach Studio")
        fit_window(window, 1000, 760, 660, 470)
        self.process = None
        self.arena = None
        self.events = queue.Queue()
        self.paths = {}
        self.selected = None
        self.dirty = False
        self.loading = False
        self.run = None
        self.variables = {}
        self.skipped = set()
        self.undo_stack = []
        self.batch = {"split": "train", "group": ""}
        self.queue_active = False
        for folder in ("runs", "labels"):
            (DATA / folder).mkdir(parents=True, exist_ok=True)
        self.build()
        self.refresh()
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.after(100, self.poll)

    def build(self):
        bar = ttk.Frame(self.window, padding=12)
        bar.pack(fill="x")
        for text, action in (("Play & collect…", self.play),
                             ("Import replays…", self.import_runs),
                             ("Refresh", self.refresh),
                             ("Open Unity project", self.open_unity)):
            ttk.Button(bar, text=text, command=action).pack(side="left", padx=(0, 4))
        self.status = tk.StringVar(value="Import Unity runs to begin.")
        ttk.Entry(self.window, textvariable=self.status, state="readonly").pack(fill="x", padx=12)

        main = ttk.Panedwindow(self.window, orient="horizontal")
        main.pack(fill="both", expand=True, padx=12)
        left = ttk.Frame(main)
        main.add(left, weight=1)
        self.tree = ttk.Treeview(left, columns=("goals", "time", "label"), selectmode="browse")
        self.tree.heading("#0", text="Replay")
        self.tree.column("#0", width=110, minwidth=45)
        for name, title in (("goals", "Goals"), ("time", "Seconds"), ("label", "Label")):
            self.tree.heading(name, text=title)
            self.tree.column(name, width=56, minwidth=48, stretch=False)
        scroll = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self.select)
        self.tree.bind("<Command-c>", self.copy_replay_id)
        self.tree.bind("<KeyPress>", self.queue_key)

        review_panel = ttk.Frame(main, padding=(8, 0))
        main.add(review_panel, weight=2)
        tabs = self.tabs = ttk.Notebook(review_panel)
        tabs.pack(fill="both", expand=True)
        label = ttk.Frame(tabs)
        raw = ttk.Frame(tabs)
        tabs.add(label, text="Review & label")
        tabs.add(raw, text="Full replay JSON")
        raw_panel, self.raw = text_panel(raw, width=1, height=1, font=("Menlo", 11))
        raw_panel.pack(fill="both", expand=True)

        controls = ttk.Frame(label, padding=(8, 4))
        controls.pack(side="bottom", fill="x")
        ttk.Button(controls, text="Save label", command=self.save_label).pack(side="left")
        ttk.Button(controls, text="Scoring guide", command=lambda: self.open_path(
            ROOT.parent / "WINDOWS-TRAINING.md")).pack(side="left", padx=8)
        ttk.Button(controls, text="Copy replay ID", command=self.copy_replay_id).pack(side="left")
        queue_bar = ttk.Frame(label, padding=(8, 4))
        queue_bar.pack(side="top", fill="x")
        for title, action in (("Label next run", self.label_next), ("Skip", self.skip_run),
                              ("Undo", self.undo_label)):
            ttk.Button(queue_bar, text=title, command=action).pack(side="left", padx=(0, 3))
        self.queue_caption = tk.StringVar(value="Label next run to start.")
        ttk.Label(label, textvariable=self.queue_caption, padding=(8, 0)).pack(side="top", anchor="w")
        form = scroll_form(label)
        self.canvas = tk.Canvas(form, height=130, width=1, bg="#101c2b", highlightthickness=0)
        self.canvas.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.canvas.bind("<Configure>", lambda _: self.draw())
        ttk.Label(form, text="Yellow goals · gray blocks · cyan route",
                  font=("Helvetica", 10)).grid(row=1, column=0, columnspan=2, sticky="w")
        self.evidence = CopyText(form, height=4, width=1, font=("Helvetica", 11))
        self.evidence.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        self.suggestion = tk.StringVar(value="Suggested rating")
        self.suggest_button = ttk.Button(form, textvariable=self.suggestion,
                                         command=self.use_suggestion, state="disabled")
        self.suggest_button.grid(row=3, column=0, columnspan=2, sticky="w", pady=3)
        self.ignore_duplicates = tk.BooleanVar(value=True)
        ttk.Checkbutton(form, text="Skip near-duplicates", variable=self.ignore_duplicates).grid(
            row=7, column=0, columnspan=2, sticky="w", pady=3)
        ttk.Button(form, text="Reset skipped runs", command=self.reset_skipped).grid(
            row=8, column=0, columnspan=2, sticky="w")
        form.columnconfigure(1, weight=1)
        fields = [
            ("rating", "Rating (1–10)", ""),
            ("split", "Dataset split", "train"),
            ("group", "Session group (optional)", ""),
        ]
        for row, (key, title, default) in enumerate(fields, start=4):
            ttk.Label(form, text=title).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=3)
            value = tk.StringVar(value=default)
            self.variables[key] = value
            value.trace_add("write", lambda *_, field=key: self.changed(field))
            if key == "split":
                entry = ttk.Combobox(form, textvariable=value, values=("train", "test"), state="readonly")
            else:
                entry = ttk.Entry(form, textvariable=value, width=12)
            entry.grid(row=row, column=1, sticky="ew", pady=3)
        activity = ttk.LabelFrame(main, text="Activity log", padding=6)
        main.add(activity, weight=2)
        log_panel, self.log = text_panel(activity, width=21, height=3, font=("Menlo", 10))
        log_panel.pack(fill="both", expand=True)

        bottom = ttk.LabelFrame(self.window, text="Datasets and training", padding=10)
        bottom.pack(fill="x", padx=12, pady=10)
        self.epochs = tk.StringVar(value="3")
        self.context = tk.StringVar(value="4096")
        settings = ttk.Frame(bottom)
        settings.pack(fill="x")
        actions = ttk.Frame(bottom)
        actions.pack(fill="x", pady=(4, 0))
        ttk.Label(settings, text="Epochs").pack(side="left")
        ttk.Entry(settings, textvariable=self.epochs, width=4).pack(side="left", padx=5)
        ttk.Label(settings, text="Context").pack(side="left")
        ttk.Entry(settings, textvariable=self.context, width=6).pack(side="left", padx=5)
        ttk.Button(settings, text="Evaluate ratings…", command=self.evaluate).pack(side="left", padx=5)
        coach_options = ttk.Menubutton(settings, text="Coach options")
        menu = tk.Menu(coach_options, tearoff=False)
        menu.add_command(label="Choose another adapter…", command=lambda: self.coach("choose"))
        menu.add_command(label="Use base model", command=lambda: self.coach("base"))
        coach_options.configure(menu=menu)
        coach_options.pack(side="left", padx=5)
        for text, action in (("Export datasets", self.export),
                             ("Train new adapter", self.train),
                             ("Start coach", self.coach),
                             ("Stop job", self.stop),
                             ("Data folder", lambda: self.open_path(DATA))):
            ttk.Button(actions, text=text, command=action).pack(side="left", padx=(0, 3))

    def copy_replay_id(self, _event=None):
        if self.selected:
            self.raw.copy(self.selected.stem)
        return "break"

    def changed(self, field):
        if self.loading:
            return
        if field in self.batch and (self.selected is None or not self.label_path(self.selected).exists()):
            self.batch[field] = self.variables[field].get().strip()
        if self.selected is not None:
            self.dirty = True

    @staticmethod
    def label_path(path):
        return DATA / "labels" / path.name

    def use_suggestion(self):
        if self.run:
            self.variables["rating"].set(str(suggested_rating(self.run)))
            if self.queue_active:
                self.tree.focus_set()

    def reset_skipped(self):
        self.skipped.clear()
        self.label_next()

    def queue_key(self, event):
        if not self.queue_active or self.selected is None or self.label_path(self.selected).exists():
            return
        if event.state & (0x4 | 0x8 | 0x10):
            return
        if event.char in "0123456789" and len(event.char) == 1:
            self.variables["rating"].set(str(int(event.char) or 10))
            self.save_label()
            return "break"
        if event.keysym == "Return" and self.variables["rating"].get():
            self.save_label()
            return "break"
        if event.keysym == "space":
            self.skip_run()
            return "break"

    def label_next(self):
        if not self.discard():
            return
        self.dirty = False
        self.queue_active = True
        self.tabs.select(0)
        labeled = {}
        if self.ignore_duplicates.get():
            for path in self.paths.values():
                if not self.label_path(path).exists():
                    continue
                try:
                    run = read(path)
                    labeled.setdefault(layout_and_outcome(run), []).append(run)
                except (OSError, ValueError, KeyError, TypeError):
                    continue
        duplicates = 0
        for row, path in self.paths.items():
            if path in self.skipped or self.label_path(path).exists():
                continue
            if labeled:
                try:
                    run = read(path)
                    if any(near_duplicate(run, other)
                           for other in labeled.get(layout_and_outcome(run), [])):
                        duplicates += 1
                        continue
                except (OSError, ValueError, KeyError, TypeError):
                    continue
            self.tree.selection_set(row)
            self.tree.see(row)
            self.tree.focus(row)
            self.select(None)
            self.tree.focus_set()
            self.queue_caption.set("1–9 rate · 0 = 10 · Space skips")
            return
        self.queue_active = False
        self.queue_caption.set(f"Queue done · {len(self.skipped)} skipped · {duplicates} near-duplicates")

    def skip_run(self):
        if self.selected is None or not self.discard():
            return
        self.skipped.add(self.selected)
        self.dirty = False
        self.label_next()

    def undo_label(self):
        if not self.undo_stack or not self.discard():
            return
        path, previous, written = self.undo_stack[-1]
        target = self.label_path(path)
        try:
            if not target.exists() or target.read_bytes() != written:
                raise ValueError("The label changed outside Studio.")
            if previous is None:
                target.unlink()
            else:
                temporary = target.with_suffix(".tmp")
                temporary.write_bytes(previous)
                temporary.replace(target)
        except (OSError, ValueError) as error:
            messagebox.showerror("Could not undo", str(error))
            return
        self.undo_stack.pop()
        self.dirty = False
        self.selected = None
        self.skipped.discard(path)
        for row, candidate in self.paths.items():
            if candidate == path:
                self.tree.set(row, "label", read(target)["split"] if previous else "unlabeled")
                self.tree.selection_set(row)
                self.tree.see(row)
                self.select(None)
                self.tree.focus(row)
                self.tree.focus_set()
                if previous is None:
                    self.queue_active = True
                    self.queue_caption.set("1–9 rate · 0 = 10 · Space skips")
                break
        self.status.set(f"Undid label for {path.stem}")

    def discard(self):
        return not self.dirty or messagebox.askyesno("Unsaved label", "Discard unsaved label changes?")

    def refresh(self):
        if not self.discard():
            return
        self.loading = True
        self.tree.delete(*self.tree.get_children())
        self.paths.clear()
        self.selected = None
        self.run = None
        self.raw.replace("")
        self.evidence.replace("")
        self.suggestion.set("Suggested rating")
        self.suggest_button.configure(state="disabled")
        self.dirty = False
        labeled = 0
        for path in sorted((DATA / "runs").glob("*.json")):
            try:
                run = read(path)
                label_path = DATA / "labels" / path.name
                state = "unlabeled"
                if label_path.exists():
                    state = read(label_path)["split"]
                    labeled += 1
                key = self.tree.insert("", "end", text=path.stem, values=(
                    f"{len(run['hits'])}/{len(run['level']['goals'])}", f"{run['duration']:.1f}", state))
                self.paths[key] = path
            except (ValueError, KeyError, TypeError, OSError) as error:
                self.append(f"Skipped {path.name}: {error}\n")
        self.loading = False
        self.status.set(f"{len(self.paths)} replays · {labeled} labeled")
        self.draw()

    def select(self, _):
        selection = self.tree.selection()
        if self.loading or not selection:
            return
        path = self.paths[selection[0]]
        if path == self.selected:
            return
        if not self.discard():
            previous = next((key for key, value in self.paths.items() if value == self.selected), None)
            if previous:
                self.tree.selection_set(previous)
            return
        try:
            run = read(path)
            label_path = DATA / "labels" / path.name
            label = read(label_path) if label_path.exists() else None
            self.run = run
            self.selected = path
            self.loading = True
            review = label["review"] if label else {}
            values = dict(rating=str(review.get("rating", "")),
                          split=label["split"] if label else self.batch["split"],
                          group=label.get("group", "") if label else self.batch["group"])
            for key, value in values.items():
                self.variables[key].set(value)
            self.raw.replace(json.dumps(run, indent=2))
            summary = summarize(run)
            reference = summary["reference_goal_center_units"]
            efficiency = summary["route_efficiency_estimate"]
            distance = summary["distance_units"]
            route_text = f"{distance:g} units traveled" if distance is not None else "Distance unavailable"
            if reference is not None:
                route_text += f" · {reference:g} via hit goal centers"
            if efficiency is not None:
                route_text += f" · {efficiency:.0%} estimated efficiency"
            self.evidence.replace(
                f"{summary['goals_hit']}/{summary['goals_total']} goals · "
                f"{summary['time_seconds']:g}/{summary['time_limit_seconds']:g}s · "
                f"{summary['idle_input_seconds']:g}s idle input\n{route_text}")
            self.suggestion.set(f"Use rubric suggestion {baseline_rating(summary)}/10")
            self.suggest_button.configure(state="normal")
            self.dirty = False
            self.draw()
        except (ValueError, KeyError, TypeError, OSError) as error:
            messagebox.showerror("Replay could not load", str(error))
        finally:
            self.loading = False

    def draw(self):
        self.canvas.delete("all")
        if not self.run:
            self.canvas.create_text(200, 70, text="Choose a replay to inspect its route.", fill="white")
            return
        width, height = self.canvas.winfo_width(), self.canvas.winfo_height()
        scale = min((width-30)/18, (height-20)/10)
        def point(p):
            return width/2+p["x"]*scale, height/2-p["y"]*scale
        self.canvas.create_rectangle(width/2-9*scale, height/2-5*scale,
                                     width/2+9*scale, height/2+5*scale, outline="#54717c")
        half = OBSTACLE_SIZE * scale / 2
        for obstacle in self.run["level"].get("obstacles") or []:
            x, y = point(obstacle)
            self.canvas.create_rectangle(x-half, y-half, x+half, y+half, fill="#667b91", outline="")
        for i, goal in enumerate(self.run["level"]["goals"]):
            x, y = point(goal)
            self.canvas.create_rectangle(x-4,y-4,x+4,y+4, fill="#ffcc42", outline="")
            self.canvas.create_text(x,y-12,text=str(i),fill="white")
        positions = [event["position"] for event in self.run["inputs"] if "position" in event]
        if self.run.get("finalPosition"):
            positions.append(self.run["finalPosition"])
        coordinates = [coordinate for position in positions for coordinate in point(position)]
        if len(coordinates) >= 4:
            self.canvas.create_line(*coordinates, fill="#51ddd0", width=2)
        for position in positions:
            x,y = point(position)
            self.canvas.create_oval(x-2,y-2,x+2,y+2,fill="#51ddd0",outline="")

    def save_label(self):
        if self.selected is None:
            messagebox.showinfo("Choose a replay", "Import and select a replay first.")
            return
        try:
            values = {key: value.get().strip() for key, value in self.variables.items()}
            review = validate_rating({"rating": int(values["rating"])})
            if values["group"]:
                for path in (DATA / "labels").glob("*.json"):
                    if path.name == self.selected.name:
                        continue
                    other = read(path)
                    if other.get("group") == values["group"] and other["split"] != values["split"]:
                        raise ValueError("This group already has labels in the other dataset split.")
            target = self.label_path(self.selected)
            previous = target.read_bytes() if target.exists() else None
            temporary = target.with_suffix(".tmp")
            temporary.write_text(json.dumps(dict(review=review, split=values["split"],
                                                  group=values["group"]), indent=2), encoding="utf-8")
            written = temporary.read_bytes()
            temporary.replace(target)
            self.undo_stack.append((self.selected, previous, written))
            self.dirty = False
            self.tree.set(self.tree.selection()[0], "label", values["split"])
            self.status.set(f"Saved label for {self.selected.stem}")
            if self.queue_active:
                self.label_next()
        except (ValueError, KeyError, TypeError, OSError) as error:
            messagebox.showerror("Label needs attention", str(error))

    def import_runs(self):
        if not self.discard():
            return
        source = filedialog.askdirectory(title="Choose Unity Runs folder",
            initialdir=str(DEFAULT_RUNS if DEFAULT_RUNS.exists() else Path.home()))
        if source:
            self.start_job([str(PYTHON), "workspace.py", "collect", "--source", source], "Import")

    def export(self):
        if self.dirty:
            messagebox.showinfo("Save label", "Save your label before exporting.")
            return
        self.start_job([str(PYTHON), "workspace.py", "export"], "Export")

    def train(self):
        if self.dirty:
            messagebox.showinfo("Save label", "Save your label before training.")
            return
        if self.busy():
            return
        try:
            epochs, context = int(self.epochs.get()), int(self.context.get())
            if not 1 <= epochs <= 100 or not 512 <= context <= 32768:
                raise ValueError("Use 1–100 epochs and context between 512 and 32768.")
            result = subprocess.run([str(PYTHON), "workspace.py", "export"],
                cwd=ROOT, capture_output=True, text=True)
            self.append(result.stdout + result.stderr)
            if result.returncode:
                return
            destination = ROOT / "adapters" / datetime.datetime.now().strftime("coach-%Y%m%d-%H%M%S-%f")
            self.start_job([str(PYTHON), "-u", "train_lora.py", "--model",
                "models/qwen2.5-0.5b-instruct", "--data", "data/train.jsonl", "--output",
                str(destination), "--epochs", str(epochs), "--context", str(context)], "Training")
            self.append(f"New adapter output: {destination}\n")
        except (ValueError, OSError) as error:
            messagebox.showerror("Training could not start", str(error))

    def evaluate(self):
        if self.busy():
            return
        test = DATA / "test.jsonl"
        if not test.exists() or not test.stat().st_size:
            messagebox.showinfo("Held-out ratings needed", "Label some test runs and export the datasets first.")
            return
        use_adapter = messagebox.askyesnocancel("Evaluate ratings",
            "Evaluate a trained adapter?\nYes: choose an adapter folder\nNo: evaluate the base model")
        if use_adapter is None:
            return
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        command = [str(PYTHON), "-u", "evaluate_coach.py", "--model",
                   "models/qwen2.5-0.5b-instruct", "--output",
                   str(DATA / "evaluations" / f"ratings-{stamp}.json")]
        if use_adapter:
            folder = self.choose_adapter()
            if folder is None:
                return
            command += ["--adapter", str(folder)]
        self.start_job(command, "Evaluation")

    @staticmethod
    def is_adapter(folder):
        return all((folder / name).is_file()
                   for name in ("adapter_model.safetensors", "adapter_config.json"))

    def choose_adapter(self):
        starting_folder = DEFAULT_ADAPTER if self.is_adapter(DEFAULT_ADAPTER) else ROOT / "adapters"
        path = filedialog.askdirectory(title="Choose adapter folder",
                                       initialdir=str(starting_folder if starting_folder.is_dir() else ROOT))
        if not path:
            return None
        folder = Path(path)
        if not self.is_adapter(folder):
            messagebox.showerror("Invalid adapter",
                                 "Choose a folder with adapter_model.safetensors and adapter_config.json.")
            return None
        return folder

    def coach(self, selection="default"):
        if self.busy():
            return
        command = [str(PYTHON), "-u", "server.py", "--model", "models/qwen2.5-0.5b-instruct"]
        if selection != "base":
            folder = DEFAULT_ADAPTER
            if selection == "choose" or not self.is_adapter(folder):
                folder = self.choose_adapter()
            if folder is None:
                return
            command += ["--adapter", str(folder)]
        self.start_job(command, "Coach")

    def busy(self):
        if self.process is not None and self.process.poll() is None:
            messagebox.showinfo("Job running", "Stop the current job before starting another.")
            return True
        return False

    def start_job(self, command, name):
        if self.busy():
            return
        try:
            child = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True, bufsize=1)
        except OSError as error:
            messagebox.showerror("Job could not start", str(error))
            return
        self.process = child
        self.status.set(name + " running…")
        def read_output():
            for line in child.stdout:
                self.events.put(("log", line))
            code = child.wait()
            self.events.put(("done", (child, name, code)))
        threading.Thread(target=read_output, daemon=True).start()

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "log":
                    self.append(value)
                else:
                    child, name, code = value
                    if child is self.process:
                        self.process = None
                        self.status.set(f"{name} finished · exit code {code}")
                        if name == "Import" and code == 0:
                            self.refresh()
        except queue.Empty:
            pass
        self.window.after(100, self.poll)

    def append(self, text):
        follow = self.log.yview()[1] >= 0.999 and not self.log.tag_ranges("sel")
        self.log.configure(state="normal")
        self.log.insert("end", text)
        # Bound terminal history during long training sessions.
        if int(self.log.index("end-1c").split(".")[0]) > 2000:
            self.log.delete("1.0", "1000.0")
        if follow:
            self.log.see("end")
        self.log.configure(state="disabled")

    def stop(self):
        if self.process and self.process.poll() is None:
            if messagebox.askyesno("Stop job", "Stop the current job? An interrupted training checkpoint may be incomplete."):
                self.process.terminate()

    def close(self):
        if not self.discard():
            return
        if self.process and self.process.poll() is None:
            if not messagebox.askyesno("Job running", "Stop the running job and close Studio?"):
                return
            self.process.terminate()
        if self.arena and self.arena.window.winfo_exists():
            self.arena.close()
            if self.arena.window.winfo_exists():
                return
        self.window.destroy()

    def play(self):
        if self.arena and self.arena.window.winfo_exists():
            self.arena.window.lift()
        else:
            self.arena = PlayArena(self.window, self.save_run)

    def save_run(self, run):
        path = DATA / "runs" / (run["id"] + ".json")
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(run, indent=2, allow_nan=False), encoding="utf-8")
        temporary.replace(path)
        count = len(run["level"]["goals"])
        row = self.tree.insert("", "end", text=path.stem, values=(
            f"{len(run['hits'])}/{count}", f"{run['duration']:.1f}", "unlabeled"))
        self.paths[row] = path
        self.tree.see(row)
        if not self.dirty:
            self.tree.selection_set(row)
        self.status.set(f"Saved {path.stem} · {len(self.paths)} replays")

    def open_unity(self):
        subprocess.Popen(["/usr/bin/open", "-a", "Unity Hub", str(ROOT.parent)])

    @staticmethod
    def open_path(path):
        subprocess.Popen(["/usr/bin/open", str(path)])


if __name__ == "__main__":
    Studio(tk.Tk())
    tk.mainloop()
