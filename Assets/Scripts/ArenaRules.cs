using System.Collections.Generic;
using UnityEngine;

namespace CubeCoachGame
{
    internal static class ArenaRules
    {
        internal const int HalfWidth = 9;
        internal const int HalfHeight = 5;
        internal const float PlayerSize = 0.64f;
        internal const float GoalSize = 0.68f;

        internal const float ObstacleSize = 1.4f;

        internal static Level Practice()
        {
            var candidates = new List<Point>();
            for (int x = -8; x <= 8; x += 2)
            for (int y = -4; y <= 4; y += 2)
                if (x != 0 || y != 0)
                    candidates.Add(new Point(x, y));

            return new Level
            {
                title = "Practice",
                description = "Collect all four yellow cubes and steer around the gray blocks.",
                seconds = 40,
                goals = Sample(candidates, 4)
            };
        }

        internal static void PlaceObstacles(Level level)
        {
            // Centers are 3 units apart, leaving open corridors around every block.
            var candidates = new List<Point>();
            for (int x = -6; x <= 6; x += 3)
            for (int y = -3; y <= 3; y += 3)
            {
                if (x == 0 && y == 0)
                    continue;
                if (System.Array.Exists(level.goals, goal =>
                    Mathf.Abs(goal.x - x) < 1.45f && Mathf.Abs(goal.y - y) < 1.45f))
                    continue;
                candidates.Add(new Point(x, y));
            }
            level.obstacles = Sample(candidates, Random.Range(3, 6));
        }

        private static Point[] Sample(List<Point> candidates, int count)
        {
            var selected = new Point[Mathf.Min(count, candidates.Count)];
            for (int i = 0; i < selected.Length; i++)
            {
                int index = Random.Range(0, candidates.Count);
                selected[i] = candidates[index];
                candidates.RemoveAt(index);
            }
            return selected;
        }

        internal static bool IsValidReview(Review review)
        {
            if (review == null || review.rating < 1 || review.rating > 10)
                return false;

            var level = review.nextLevel;
            if (level == null)
                return string.IsNullOrWhiteSpace(review.feedback);
            if (string.IsNullOrWhiteSpace(review.feedback) || string.IsNullOrWhiteSpace(level.title) ||
                string.IsNullOrWhiteSpace(level.description) || !IsFinite(level.seconds) ||
                level.seconds < 15 || level.seconds > 90 ||
                level.goals == null || level.goals.Length < 1 || level.goals.Length > 8)
                return false;

            for (int i = 0; i < level.goals.Length; i++)
            {
                var goal = level.goals[i];
                if (goal == null || !IsFinite(goal.x) || !IsFinite(goal.y) ||
                    Mathf.Abs(goal.x) > HalfWidth - 1 || Mathf.Abs(goal.y) > HalfHeight - 1)
                    return false;

                var position = new Vector2(goal.x, goal.y);
                if (position.magnitude < 1.3f)
                    return false;

                for (int j = 0; j < i; j++)
                {
                    var other = level.goals[j];
                    if (Vector2.Distance(position, new Vector2(other.x, other.y)) < 1.4f)
                        return false;
                }
            }

            return true;
        }

        private static bool IsFinite(float value) => !float.IsNaN(value) && !float.IsInfinity(value);
    }
}
