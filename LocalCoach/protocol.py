"""Shared inference/training contract. No network or ML dependencies."""
import json
import math

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

def messages(run):
    return [{'role': 'system', 'content': SYSTEM},
            {'role': 'user', 'content': json.dumps(run, separators=(',', ':'), allow_nan=False)}]

def validate_review(value):
    if not isinstance(value, dict):
        raise ValueError('review must be a JSON object')
    if type(value.get('rating')) is not int or not 1 <= value['rating'] <= 10:
        raise ValueError('rating must be an integer from 1 to 10')
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
