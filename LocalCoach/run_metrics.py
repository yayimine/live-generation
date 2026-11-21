"""Obstacle-aware gameplay measurements shared by the coach and Studio."""
import heapq
import math

# The player center must clear a block by its half-width plus the player's radius.
CLEARANCE = 1.4 / 2 + 0.64 / 2


def xy(point):
    return point["x"], point["y"]


def crosses_block(start, end, block):
    """Check whether a line enters the rectangle's interior. Touching an edge is allowed."""
    enter, leave = 0.0, 1.0
    for origin, target, center in zip(start, end, block):
        low, high = center - CLEARANCE, center + CLEARANCE
        delta = target - origin
        if delta == 0:
            if not low < origin < high:
                return False
            continue
        first, last = sorted(((low - origin) / delta, (high - origin) / delta))
        enter, leave = max(enter, first), min(leave, last)
        if enter >= leave - 1e-10:
            return False
    return enter < leave - 1e-10


def reference_distance(waypoints, blocks):
    """Shortest continuous route through the given goal centers in the recorded order."""
    nodes = list(waypoints)
    for x, y in blocks:
        nodes.extend((x + dx, y + dy) for dx in (-CLEARANCE, CLEARANCE)
                     for dy in (-CLEARANCE, CLEARANCE)
                     if abs(x + dx) <= 8.68 and abs(y + dy) <= 4.68)
    edges = [[] for _ in nodes]
    for index, point in enumerate(nodes):
        for other_index in range(index):
            other = nodes[other_index]
            if any(crosses_block(point, other, block) for block in blocks):
                continue
            distance = math.dist(point, other)
            edges[index].append((other_index, distance))
            edges[other_index].append((index, distance))

    total = 0.0
    for start in range(len(waypoints) - 1):
        distances = {start: 0.0}
        queue = [(0.0, start)]
        while queue:
            distance, index = heapq.heappop(queue)
            if index == start + 1:
                total += distance
                break
            if distance > distances[index]:
                continue
            for neighbor, weight in edges[index]:
                candidate = distance + weight
                if candidate < distances.get(neighbor, math.inf):
                    distances[neighbor] = candidate
                    heapq.heappush(queue, (candidate, neighbor))
        else:
            return None
    return total


def summarize(run):
    level = run["level"]
    duration = run["duration"]
    distance = run.get("distance")
    hit_order = [hit["goal"] for hit in run["hits"]]
    goals = level["goals"]
    inputs = run["inputs"]
    idle = 0.0
    # Opposing inputs cancel. "Idle" measures input, not time stopped by a wall.
    for index, event in enumerate(inputs):
        mask = event["mask"]
        if bool(mask & 1) == bool(mask & 4) and bool(mask & 2) == bool(mask & 8):
            end = inputs[index + 1]["time"] if index + 1 < len(inputs) else duration
            idle += max(0.0, min(end, duration) - max(0.0, event["time"]))

    reference = None
    if hit_order and all(0 <= index < len(goals) for index in hit_order):
        waypoints = [(0, 0)] + [xy(goals[index]) for index in hit_order]
        reference = reference_distance(waypoints, [xy(block) for block in level.get("obstacles") or []])
    # A pickup can happen before the player reaches the goal center. The displayed
    # ratio is an efficiency estimate, capped at 100%, and applies to clears only.
    efficiency = None
    if run["completed"] and reference is not None and distance is not None and distance > 0:
        efficiency = min(1.0, reference / distance)

    return {
        "goals_hit": len(hit_order),
        "goals_total": len(goals),
        "completed": run["completed"],
        "time_seconds": round(duration, 2),
        "time_limit_seconds": level["seconds"],
        "idle_input_seconds": round(idle, 2),
        "distance_units": round(distance, 2) if distance is not None else None,
        "reference_goal_center_units": round(reference, 2) if reference is not None else None,
        "route_efficiency_estimate": round(efficiency, 3) if efficiency is not None else None,
    }


def baseline_rating(summary):
    goal_points = math.floor(6 * summary["goals_hit"] / max(1, summary["goals_total"]) + 0.5)
    time_points = 0
    if summary["completed"]:
        time_points = 2 if summary["time_seconds"] <= summary["time_limit_seconds"] / 2 else 1
    efficiency = summary["route_efficiency_estimate"]
    route_points = int(summary["goals_hit"] > 0)
    if efficiency is not None:
        route_points = 2 if efficiency >= 0.85 else int(efficiency >= 0.60)
    return min(10, max(1, goal_points + route_points + time_points))
