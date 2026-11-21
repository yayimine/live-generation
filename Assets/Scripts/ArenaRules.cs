using UnityEngine;

namespace CubeCoachGame
{
    internal static class ArenaRules
    {
        internal const int HalfWidth = 9;
        internal const int HalfHeight = 5;
        internal const float PlayerSize = 0.64f;
        internal const float GoalSize = 0.68f;

        internal static Level Practice() => new Level
        {
            title = "First contact",
            description = "Collect every yellow cube. Find a clean route through the arena.",
            seconds = 40,
            goals = new[] { new Point(-5, 2), new Point(5, 3), new Point(5, -3), new Point(-4, -3) }
        };

        internal static bool IsValidReview(Review review)
        {
            if (review == null || review.rating < 1 || review.rating > 10 ||
                string.IsNullOrWhiteSpace(review.feedback))
                return false;

            var level = review.nextLevel;
            if (level == null || string.IsNullOrWhiteSpace(level.title) ||
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
