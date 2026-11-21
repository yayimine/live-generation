"""Local gameplay collection, human labeling, and dataset export."""
import argparse
import json
from pathlib import Path
import shutil
import sys
from protocol import validate_review

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    collect = commands.add_parser("collect", help="Import Unity replays")
    collect.add_argument("--source", type=Path)
    label = commands.add_parser("label", help="Show a replay and enter its target review")
    label.add_argument("id")
    export = commands.add_parser("export", help="Validate labels and export train/test JSONL")
    commands.add_parser("list", help="List collected runs and label status")
    args = parser.parse_args()
    runs = DATA / "runs"
    labels = DATA / "labels"
    runs.mkdir(parents=True, exist_ok=True)
    labels.mkdir(exist_ok=True)
    if args.command == "collect":
        default = (Path.home() / "AppData/LocalLow/DefaultCompany/live generation/Runs"
                   if sys.platform == "win32" else
                   Path.home() / "Library/Application Support/DefaultCompany/live generation/Runs")
        source = args.source or default
        if not source.is_dir():
            parser.error(f"Replay folder missing: {source}. Pass the folder printed by Unity with --source.")
        count = 0
        for path in source.glob("*.json"):
            if path.name.endswith(".review.json"):
                continue
            run = read(path)
            required = ("id", "level", "inputs", "hits", "duration", "completed")
            if not all(key in run for key in required):
                continue
            # Derive the name from the source file, never from untrusted replay content.
            destination = runs / path.name
            if destination.exists():
                if read(destination) != run:
                    parser.error(f"Conflicting replay: {path.name}")
                continue
            shutil.copy2(path, destination)
            count += 1
        print(f"Imported {count} new replays into {runs}")
    elif args.command == "list":
        for path in sorted(runs.glob("*.json")):
            run = read(path)
            state = "labeled" if (labels / path.name).exists() else "unlabeled"
            print(f"{path.stem} | {len(run['hits'])}/{len(run['level']['goals'])} goals"
                  f" | {run['duration']:.1f}s | {state}")
    elif args.command == "label":
        if Path(args.id).name != args.id:
            parser.error("Use a replay ID from the list command.")
        path = runs / f"{args.id}.json"
        run = read(path)
        print(json.dumps(run, indent=2))
        print("Read the scoring rubric in WINDOWS-TRAINING.md. Enter a review grounded in this run.")
        rating = int(input("Rating (1-10): "))
        feedback = input("Feedback: ")
        title = input("Next level title: ")
        description = input("Next level description: ")
        seconds = float(input("Next level seconds (15-90): "))
        goals = json.loads(input('Goal coordinates, e.g. [{"x":-5,"y":3},{"x":5,"y":-3}]: '))
        review = validate_review(dict(rating=rating, feedback=feedback, nextLevel=dict(
            title=title, description=description, seconds=seconds, goals=goals)))
        split = input("Split (train/test): ").strip()
        if split not in ("train", "test"):
            parser.error("Choose train or test.")
        session = input("Player/session group (keep the same group in one split): ").strip()
        if not session:
            parser.error("A group is required.")
        target = labels / path.name
        if target.exists() and input("Replace existing label? (yes/no): ") != "yes":
            return
        target.write_text(json.dumps(dict(review=review, split=split, group=session), indent=2),
                          encoding="utf-8")
        print(f"Saved {target}")
    elif args.command == "export":
        groups, seen = {}, set()
        datasets = {"train": [], "test": []}
        for path in sorted(labels.glob("*.json")):
            label = read(path)
            run = read(runs / path.name)
            if run["id"] in seen:
                parser.error("Duplicate run ID")
            seen.add(run["id"])
            split, group = label["split"], label["group"]
            if split not in datasets or not group:
                parser.error(f"Invalid split or group in {path}")
            if groups.setdefault(group, split) != split:
                parser.error(f"Group {group} appears in both splits.")
            review = validate_review(label["review"])
            datasets[split].append(json.dumps(dict(run=run, review=review), allow_nan=False))
        if any(not rows for rows in datasets.values()):
            parser.error("Label at least one run in each split before exporting.")
        for split, rows in datasets.items():
            (DATA / f"{split}.jsonl").write_text("\n".join(rows) + "\n", encoding="utf-8")
            print(f"{split}: {len(rows)} runs")


if __name__ == "__main__":
    main()
