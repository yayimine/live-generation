"""Playable Studio arena and Unity-compatible replay recording."""
import json
import math
import queue
import random
import threading
import time
import tkinter as tk
from tkinter import ttk
from urllib.request import Request, urlopen
from uuid import uuid4

from protocol import validate_review
from studio_widgets import fit_window, text_panel

OBSTACLE_SIZE = 1.4
KEYS = {"w": 1, "a": 2, "s": 4, "d": 8}


def point(x, y):
    return {"x": x, "y": y}


def practice():
    candidates = [(x, y) for x in range(-8, 9, 2) for y in range(-4, 5, 2) if (x, y) != (0, 0)]
    return dict(title="Practice", description="Collect all four yellow cubes and steer around the gray blocks.",
                seconds=40, goals=[point(x, y) for x, y in random.sample(candidates, 4)])


def place_obstacles(level):
    # Wide corridors remain between the blocks and around the arena perimeter.
    candidates = [(x, y) for x in range(-6, 7, 3) for y in range(-3, 4, 3)
                  if (x, y) != (0, 0) and all(
                      abs(goal["x"] - x) >= 1.45 or abs(goal["y"] - y) >= 1.45
                      for goal in level["goals"])]
    count = min(random.randint(3, 5), len(candidates))
    return dict(level, obstacles=[point(x, y) for x, y in random.sample(candidates, count)])


class Run:
    """Mirrors Unity RunSession's movement, contacts, and replay fields."""

    def __init__(self, level):
        self.level = level
        self.id = uuid4().hex
        self.x = self.y = self.elapsed = self.distance = 0.0
        self.inputs = []
        self.hits = []
        self.collected = set()
        self.reason = None

    def step(self, mask, delta, finish=False):
        if self.reason:
            return
        if not self.inputs or self.inputs[-1]["mask"] != mask:
            self.inputs.append({"time": self.elapsed, "mask": mask, "position": point(self.x, self.y)})
        delta = min(delta, 0.05)
        self.elapsed += delta
        x = bool(mask & 8) - bool(mask & 2)
        y = bool(mask & 1) - bool(mask & 4)
        scale = 4.5 * delta / (math.hypot(x, y) or 1)
        next_x = min(8.68, max(-8.68, self.x + x * scale))
        next_y = min(4.68, max(-4.68, self.y + y * scale))
        if self.blocked(next_x, self.y):
            next_x = self.x
        if self.blocked(next_x, next_y):
            next_y = self.y
        self.distance += math.hypot(next_x - self.x, next_y - self.y)
        self.x, self.y = next_x, next_y

        for index, goal in enumerate(self.level["goals"]):
            if index not in self.collected and abs(self.x - goal["x"]) < 0.66 and abs(self.y - goal["y"]) < 0.66:
                self.collected.add(index)
                self.hits.append({"time": self.elapsed, "goal": index})
        if len(self.collected) == len(self.level["goals"]):
            self.reason = "all_goals"
        elif self.elapsed >= self.level["seconds"]:
            self.reason = "timeout"
        elif finish:
            self.reason = "enter"

    def blocked(self, x, y):
        clearance = (0.64 + OBSTACLE_SIZE) / 2
        return any(abs(x - obstacle["x"]) < clearance and abs(y - obstacle["y"]) < clearance
                   for obstacle in self.level.get("obstacles") or [])

    def replay(self):
        return dict(id=self.id, level=self.level, inputs=self.inputs, hits=self.hits,
                    duration=self.elapsed, distance=self.distance, endReason=self.reason,
                    completed=self.reason == "all_goals", finalPosition=point(self.x, self.y))


class PlayArena:
    def __init__(self, parent, save):
        self.window = tk.Toplevel(parent)
        self.window.title("Cube Coach · Play & collect")
        fit_window(self.window, 760, 570, 400, 340)
        self.save = save
        self.run = None
        self.saved = False
        self.mask = 0
        self.next_level = None
        self.reviewing = False
        self.replies = queue.Queue()
        self.summary = tk.StringVar(value="Start practice to collect a run.")
        ttk.Entry(self.window, textvariable=self.summary, state="readonly").pack(fill="x", padx=12, pady=8)
        self.canvas = tk.Canvas(self.window, bg="#101c2b", highlightthickness=0, takefocus=True)
        self.canvas.bind("<Configure>", lambda _: self.draw())
        self.canvas.bind("<Button-1>", lambda _: self.canvas.focus_set())
        self.canvas.bind("<FocusOut>", lambda _: self.release_keys())
        self.canvas.bind("<KeyPress>", self.press)
        self.canvas.bind("<KeyRelease>", self.release)
        controls = ttk.Frame(self.window, padding=10)
        controls.pack(side="bottom", fill="x")
        self.start_button = ttk.Button(controls, text="Start practice", command=lambda: self.start(practice()))
        self.finish_button = ttk.Button(controls, text="Finish run", command=self.finish, state="disabled")
        self.review_button = ttk.Button(controls, text="Ask coach", command=self.ask, state="disabled")
        self.next_button = ttk.Button(controls, text="Play generated level",
                                      command=lambda: self.start(self.next_level), state="disabled")
        for index, button in enumerate((self.start_button, self.finish_button,
                                        self.review_button, self.next_button)):
            controls.columnconfigure(index % 2, weight=1)
            button.grid(row=index // 2, column=index % 2, sticky="ew", padx=3, pady=2)
        feedback_panel, self.feedback = text_panel(self.window, width=1, height=3)
        feedback_panel.pack(side="bottom", fill="x", padx=12)
        self.feedback.replace("WASD to move · Enter to finish early")
        self.canvas.pack(fill="both", expand=True, padx=12)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.after(16, self.tick)

    def start(self, level):
        self.run = Run(place_obstacles(level))
        self.mask = 0
        self.next_level = None
        self.saved = False
        self.previous = time.monotonic()
        self.feedback.replace(level["description"] + "  WASD to move · Enter to finish early")
        self.start_button.configure(state="disabled")
        self.finish_button.configure(state="normal", text="Finish run")
        self.review_button.configure(state="disabled")
        self.next_button.configure(state="disabled")
        self.canvas.focus_set()

    def release_keys(self):
        self.mask = 0

    def press(self, event):
        if event.keysym == "Return":
            self.finish()
        else:
            self.mask |= KEYS.get(event.keysym.lower(), 0)

    def release(self, event):
        self.mask &= ~KEYS.get(event.keysym.lower(), 0)

    def finish(self):
        if self.run and not self.saved:
            self.run.step(self.mask, 0, finish=True)
            self.save_run()

    def save_run(self):
        try:
            self.save(self.run.replay())
        except OSError as error:
            self.feedback.replace(f"Could not save run: {error}")
            self.finish_button.configure(text="Retry save")
            return
        self.saved = True
        self.feedback.replace("Replay saved. Select it in Studio to label it, or ask the local coach.")
        self.start_button.configure(state="normal", text="Replay practice")
        self.finish_button.configure(state="disabled")
        self.review_button.configure(state="normal")

    def tick(self):
        if self.run and not self.run.reason:
            now = time.monotonic()
            self.run.step(self.mask, now - self.previous)
            self.previous = now
            if self.run.reason:
                self.save_run()
        if self.run:
            remaining = max(0, self.run.level["seconds"] - self.run.elapsed)
            self.summary.set(f"{self.run.level['title']}   ·   "
                             f"{len(self.run.hits)}/{len(self.run.level['goals'])} goals   ·   {remaining:.1f}s")
        if self.reviewing:
            try:
                result, error = self.replies.get_nowait()
            except queue.Empty:
                pass
            else:
                self.reviewing = False
                self.start_button.configure(state="normal")
                self.review_button.configure(state="normal")
                if error:
                    self.feedback.replace(error)
                else:
                    self.next_level = result["nextLevel"]
                    self.feedback.replace(f"{result['rating']}/10 · {result['feedback']}\n"
                                      f"{self.next_level['title']} · {self.next_level['description']}")
                    self.next_button.configure(state="normal")
        self.draw()
        self.window.after(16, self.tick)

    def draw(self):
        self.canvas.delete("all")
        width, height = self.canvas.winfo_width(), self.canvas.winfo_height()
        scale = max(1, min((width - 24) / 18, (height - 24) / 10))
        cx, cy = width / 2, height / 2
        for x in range(-9, 10):
            sx = cx + x * scale
            self.canvas.create_line(sx, cy - 5 * scale, sx, cy + 5 * scale, fill="#293c50")
        for y in range(-5, 6):
            sy = cy - y * scale
            self.canvas.create_line(cx - 9 * scale, sy, cx + 9 * scale, sy, fill="#293c50")
        self.canvas.create_rectangle(cx - 9 * scale, cy - 5 * scale,
                                     cx + 9 * scale, cy + 5 * scale, outline="#7094a8")
        if not self.run:
            return
        level = self.run.level
        for obstacle in level["obstacles"]:
            self.square(cx + obstacle["x"] * scale, cy - obstacle["y"] * scale,
                        OBSTACLE_SIZE * scale / 2, "#667b91")
        for index, goal in enumerate(level["goals"]):
            if index not in self.run.collected:
                self.square(cx + goal["x"] * scale, cy - goal["y"] * scale, scale * 0.34, "#ffcc42")
        x, y = (self.run.x, self.run.y) if self.run else (0, 0)
        self.square(cx + x * scale, cy - y * scale, scale * 0.32, "#51ddd0")

    def square(self, x, y, half_size, color):
        self.canvas.create_rectangle(x-half_size, y-half_size, x+half_size, y+half_size,
                                     fill=color, outline="")

    def ask(self):
        self.reviewing = True
        self.review_button.configure(state="disabled")
        self.start_button.configure(state="disabled")
        self.next_button.configure(state="disabled")
        self.feedback.replace("Waiting for the local coach…")
        payload = json.dumps(self.run.replay()).encode("utf-8")

        def request_review():
            try:
                request = Request("http://127.0.0.1:8765/review", data=payload,
                                  headers={"Content-Type": "application/json"})
                with urlopen(request, timeout=180) as response:
                    result = validate_review(json.load(response))
                self.replies.put((result, None))
            except (OSError, ValueError, KeyError, TypeError) as error:
                self.replies.put((None, f"Coach review unavailable. Start the coach in Studio and retry. {error}"))

        threading.Thread(target=request_review, daemon=True).start()

    def close(self):
        if self.run and not self.saved:
            self.finish()
            if not self.saved:
                return
        self.window.destroy()
