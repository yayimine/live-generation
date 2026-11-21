"""Shared inference/training contract. No network or ML dependencies."""
import json
import math

from run_metrics import summarize

SYSTEM = '''You are the coach of a top-down cube game. Review the entire run, including
all WASD state changes and goal hits. mask bits: W=1 A=2 S=4 D=8; each state lasts
until the next event or duration. Opposite directions cancel; diagonal speed is
normalized. Movement speed is 4.5 units/second. Rate gameplay from 1 to 10 based
on completion, route efficiency and time. Give brief actionable feedback.
Return ONLY a JSON object with rating (integer), feedback (string), and nextLevel:
{title:string, description:string, seconds:number, goals:[{x:number,y:number}]}.
Use this exact JSON structure, with your own values:
{"rating":7,"feedback":"Choose a route before moving.","nextLevel":{"title":"Two goals","description":"Collect the two goals on opposite sides.","seconds":35,"goals":[{"x":-5,"y":3},{"x":5,"y":-3}]}}
nextLevel must be an object and goals must be an array of coordinate objects.
The replay may include level.obstacles, which are solid 1.4-unit square blocks.
Consider those blocks when evaluating the route. For the next level, specify goals;
the game adds blocks with open routes around them. Player starts at (0,0).
Include 1 to 8 yellow
goals, each within x [-8,8], y [-4,4], at least 1.3 from origin and 1.4 apart.
seconds must be 15 to 90, sufficient for the route. Describe exactly the level
you generate. Adapt its challenge to demonstrated skill. Do not invent hits.'''

RATING_SYSTEM = """Rate this Cube Coach run from 1 to 10 using goal completion,
route efficiency, and time. Consider any solid blocks recorded in level.obstacles.
Use the actual hits and input history. Return only JSON, for example {"rating":7}.
The rating must be an integer."""

def messages(run, rating_only=False, include_summary=True, condensed=False):
    instructions = RATING_SYSTEM if rating_only else SYSTEM
    if include_summary and "level" in run:
        summary = json.dumps(summarize(run), separators=(',', ':'), allow_nan=False)
        instructions += ("\nComputed facts for this replay follow. The route reference goes "
                         "around blocks through hit goal centers in recorded order. Use its "
                         "efficiency as an estimate for clears. Null means unavailable. "
                         "Idle input means no net direction, including opposing keys.\n" + summary)
    if condensed:
        # Aggregate the full input history without changing the saved replay.
        durations = {}
        events = run["inputs"]
        for index, event in enumerate(events):
            end = events[index + 1]["time"] if index + 1 < len(events) else run["duration"]
            seconds = max(0.0, min(end, run["duration"]) - max(0.0, event["time"]))
            mask = event["mask"]
            durations[mask] = durations.get(mask, 0.0) + seconds
        run = {key: value for key, value in run.items() if key not in ("id", "inputs")}
        run["input_summary"] = {
            "event_count": len(events),
            "seconds_by_mask": {mask: round(seconds, 3) for mask, seconds in sorted(durations.items())},
        }
        instructions += ("\nThis replay uses input_summary instead of individual input events. "
                         "Mask bits are W=1 A=2 S=4 D=8. Use the aggregate times, goals, "
                         "and computed facts. Do not infer individual turns from the summary.")
    return [{'role': 'system', 'content': instructions},
            {'role': 'user', 'content': json.dumps(run, separators=(',', ':'), allow_nan=False)}]

def validate_rating(value):
    if not isinstance(value, dict):
        raise ValueError('review must be a JSON object')
    if type(value.get('rating')) is not int or not 1 <= value['rating'] <= 10:
        raise ValueError('rating must be an integer from 1 to 10')
    return {"rating": value["rating"]}

def validate_review(value):
    validate_rating(value)
    if set(value) <= {"rating", "source", "notice"}:
        return value
    if not isinstance(value.get('feedback'), str) or not value['feedback'].strip():
        raise ValueError('feedback is required')
    level = value['nextLevel']
    if not isinstance(level, dict):
        raise ValueError('nextLevel must be a JSON object')
    for key in ('title', 'description'):
        if not isinstance(level.get(key), str) or not level[key].strip():
            raise ValueError(f'{key} is required')
    def number(n):
        return type(n) in (int, float) and math.isfinite(n)
    if not number(level.get('seconds')) or not 15 <= level['seconds'] <= 90:
        raise ValueError('seconds must be 15..90')
    goals = level['goals']
    if not isinstance(goals, list) or not 1 <= len(goals) <= 8:
        raise ValueError('expected 1..8 goals')
    for i, p in enumerate(goals):
        x, y = p['x'], p['y']
        if not number(x) or not number(y) or abs(x) > 8 or abs(y) > 4 or math.hypot(x,y) < 1.3:
            raise ValueError('goal outside playable region or on spawn')
        if any(math.hypot(x-q['x'], y-q['y']) < 1.4 for q in goals[:i]):
            raise ValueError('goals overlap')
    return value
