"""Compare the rubric and a local coach against held-out human ratings."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter

from protocol import validate_rating
from run_metrics import baseline_rating, summarize


def read_rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def metrics(pairs):
    errors = [abs(expected - actual) for expected, actual in pairs]
    return {
        "count": len(errors),
        "mean_absolute_error": round(sum(errors) / len(errors), 3) if errors else None,
        "within_one": sum(error <= 1 for error in errors),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--adapter")
    parser.add_argument("--test", type=Path, default=Path("data/test.jsonl"))
    parser.add_argument("--train", type=Path, default=Path("data/train.jsonl"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    rows = read_rows(args.test)
    if not rows:
        parser.error("Export a dataset with held-out test ratings first.")
    ids = [row["run"]["id"] for row in rows]
    if len(set(ids)) != len(ids):
        parser.error("The test dataset has repeated run IDs.")
    if args.train.is_file() and set(ids) & {row["run"]["id"] for row in read_rows(args.train)}:
        parser.error("Some test run IDs are also in the training dataset.")

    command = [sys.executable, "-u", str(Path(__file__).with_name("server.py")),
               "--stdio", "--model", args.model]
    command += ["--adapter", args.adapter] if args.adapter else ["--rating-only"]
    records = []
    with subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                          text=True, encoding="utf-8") as coach:
        line = coach.stdout.readline()
        if not line or not json.loads(line).get("ready"):
            raise SystemExit("The local coach could not start.")
        for row in rows:
            run = row["run"]
            expected = validate_rating(row["review"])["rating"]
            baseline = baseline_rating(summarize(run))
            start = perf_counter()
            coach.stdin.write(json.dumps(run, allow_nan=False) + "\n")
            coach.stdin.flush()
            line = coach.stdout.readline()
            seconds = round(perf_counter() - start, 3)
            if not line:
                raise SystemExit("The local coach exited before finishing evaluation.")
            reply = json.loads(line)
            try:
                if isinstance(reply, dict) and reply.get("source") == "gameplay rubric":
                    raise ValueError(reply["notice"])
                actual = validate_rating(reply)["rating"]
                error = None
            except ValueError as exc:
                actual = None
                error = reply.get("error", str(exc)) if isinstance(reply, dict) else str(exc)
            records.append(dict(id=run["id"], human=expected, baseline=baseline, model=actual,
                                seconds=seconds, error=error))
            print(f"{len(records)}/{len(rows)} · human {expected} · baseline {baseline} · "
                  f"model {actual if actual is not None else error} · {seconds:.2f}s", flush=True)
        coach.stdin.close()

    valid = [row for row in records if row["model"] is not None]
    report = {
        "model": args.model,
        "adapter": args.adapter,
        "test": str(args.test),
        "total": len(records),
        "baseline_all": metrics([(row["human"], row["baseline"]) for row in records]),
        "baseline_on_model_valid_runs": metrics([(row["human"], row["baseline"]) for row in valid]),
        "model_on_valid_runs": metrics([(row["human"], row["model"]) for row in valid]),
        "model_within_one_of_all_runs": sum(abs(row["human"] - row["model"]) <= 1 for row in valid),
        "runs": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Valid replies: {len(valid)}/{len(rows)}")
    print("Mean absolute error on the same valid runs:",
          report["baseline_on_model_valid_runs"]["mean_absolute_error"], "baseline ·",
          report["model_on_valid_runs"]["mean_absolute_error"], "model")
    print(f"Report: {args.output}")


if __name__ == "__main__":
    main()
