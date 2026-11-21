using System;
using UnityEngine;

namespace CubeCoachGame
{
    // Owns movement and replay events independently of rendering and input devices.
    internal sealed class RunSession
    {
        private const float Speed = 4.5f;
        private const float ContactRange = (ArenaRules.PlayerSize + ArenaRules.GoalSize) / 2;
        internal const int Up = 1, Left = 2, Down = 4, Right = 8;

        private readonly bool[] collected;
        private int lastMask = -1;

        internal Run Replay { get; }
        internal Vector2 Position { get; private set; }
        internal float Elapsed { get; private set; }
        internal bool Finished => Replay.endReason != null;

        internal RunSession(Level level)
        {
            Replay = new Run { id = Guid.NewGuid().ToString("N"), level = level };
            collected = new bool[level.goals.Length];
        }

        internal void ReleaseInput()
        {
            if (!Finished)
                RecordInput(0);
        }

        internal void Step(int mask, float deltaTime, bool finishRequested)
        {
            if (Finished)
                return;

            RecordInput(mask);
            float step = Mathf.Min(deltaTime, 0.05f);
            Elapsed += step;

            var direction = new Vector2(
                Axis(mask, Right, Left), Axis(mask, Up, Down)).normalized;
            var next = Position + direction * Speed * step;
            const float limitX = ArenaRules.HalfWidth - ArenaRules.PlayerSize / 2;
            const float limitY = ArenaRules.HalfHeight - ArenaRules.PlayerSize / 2;
            next.x = Mathf.Clamp(next.x, -limitX, limitX);
            next.y = Mathf.Clamp(next.y, -limitY, limitY);
            // Resolve the axes separately so the player can slide along blocks.
            if (Blocked(next.x, Position.y))
                next.x = Position.x;
            if (Blocked(next.x, next.y))
                next.y = Position.y;
            Replay.distance += Vector2.Distance(Position, next);
            Position = next;

            for (int i = 0; i < collected.Length; i++)
            {
                var goal = Replay.level.goals[i];
                if (collected[i] || Mathf.Abs(Position.x - goal.x) >= ContactRange ||
                    Mathf.Abs(Position.y - goal.y) >= ContactRange)
                    continue;

                collected[i] = true;
                Replay.hits.Add(new Hit { time = Elapsed, goal = i });
            }

            bool completed = Replay.hits.Count == collected.Length;
            bool timedOut = Elapsed >= Replay.level.seconds;
            if (!completed && !timedOut && !finishRequested)
                return;

            Replay.duration = Elapsed;
            Replay.completed = completed;
            Replay.endReason = completed ? "all_goals" : timedOut ? "timeout" : "enter";
            Replay.finalPosition = new Point(Position.x, Position.y);
        }

        private bool Blocked(float x, float y)
        {
            var obstacles = Replay.level.obstacles;
            if (obstacles == null)
                return false;
            const float clearance = (ArenaRules.PlayerSize + ArenaRules.ObstacleSize) / 2;
            foreach (var obstacle in obstacles)
                if (Mathf.Abs(x - obstacle.x) < clearance && Mathf.Abs(y - obstacle.y) < clearance)
                    return true;
            return false;
        }

        private void RecordInput(int mask)
        {
            if (mask == lastMask)
                return;
            Replay.inputs.Add(new InputEvent
            {
                time = Elapsed,
                mask = mask,
                position = new Point(Position.x, Position.y)
            });
            lastMask = mask;
        }

        private static int Axis(int mask, int positive, int negative) =>
            ((mask & positive) != 0 ? 1 : 0) - ((mask & negative) != 0 ? 1 : 0);
    }
}
