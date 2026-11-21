"""Run statistics and conservative duplicate checks for the labeling queue."""
import math


from run_metrics import baseline_rating, summarize


def suggested_rating(run):
    return baseline_rating(summarize(run))


def layout_and_outcome(run):
    level = run["level"]
    return (
        tuple((p["x"], p["y"]) for p in level["goals"]),
        tuple(sorted((p["x"], p["y"]) for p in level.get("obstacles") or [])),
        level["seconds"], run.get("endReason"), run["completed"],
        tuple(hit["goal"] for hit in run["hits"]),
    )


def route(run):
    positions = [(0, 0)]
    for event in run.get("inputs", []):
        if "position" in event:
            p = event["position"]
            position = p["x"], p["y"]
            if math.dist(position, positions[-1]) >= 0.5:
                positions.append(position)
    final = run.get("finalPosition")
    if final:
        positions.append((final["x"], final["y"]))
    return positions


def near_duplicate(first, second):
    if abs(first["duration"] - second["duration"]) > 1:
        return False
    if abs(first.get("distance", 0) - second.get("distance", 0)) > 1:
        return False
    a, b = route(first), route(second)
    return len(a) == len(b) and all(math.dist(p, q) <= 0.75 for p, q in zip(a, b))
