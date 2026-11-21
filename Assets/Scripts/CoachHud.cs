using UnityEngine;

namespace CubeCoachGame
{
    internal sealed class CoachHud
    {
        internal enum Action { None, NextLevel, Retry, Practice }

        private GUIStyle heading, body, detail, button;
        private Vector2 reviewScroll;

        internal Action Draw(RunSession session, int stage, bool waiting, Review review,
            string status, string saveError)
        {
            InitStyles();
            var previousMatrix = GUI.matrix;
            float scale = Mathf.Min(Screen.width / 1100f, Screen.height / 800f);
            GUI.matrix = Matrix4x4.Scale(Vector3.one * scale);
            try
            {
                return DrawLayout(session, stage, waiting, review, status, saveError,
                    Screen.width / scale, Screen.height / scale);
            }
            finally
            {
                GUI.matrix = previousMatrix;
            }
        }

        private Action DrawLayout(RunSession session, int stage, bool waiting, Review review,
            string status, string saveError, float width, float height)
        {
            var run = session.Replay;
            var level = run.level;
            GUI.Label(new Rect(35, 20, width - 70, 45), "CUBE / COACH", heading);
            GUI.Label(new Rect(35, 65, width - 70, 30), level.description, body);
            GUI.Label(new Rect(35, height - 78, width - 70, 30),
                "W A S D   move      ·      ENTER   finish run      ·      Collect every yellow cube", body);
            float remaining = Mathf.Max(0, level.seconds - session.Elapsed);
            GUI.Label(new Rect(35, height - 45, width - 70, 25),
                $"LEVEL {stage:00}  /  {level.title}       GOALS {run.hits.Count}/{level.goals.Length}       {remaining:0.0}s",
                detail);
            if (!session.Finished)
            {
                reviewScroll = Vector2.zero;
                return Action.None;
            }

            var panel = new Rect(width / 2 - 290, height / 2 - 250, 580, 500);
            var previousColor = GUI.color;
            GUI.color = new Color(0.06f, 0.09f, 0.14f, 0.98f);
            GUI.DrawTexture(panel, Texture2D.whiteTexture);
            GUI.color = previousColor;

            GUILayout.BeginArea(new Rect(panel.x + 25, panel.y + 20, 530, 460));
            string title = waiting ? "Thinking locally…" : "Run finished";
            if (review != null)
                title = $"{review.rating} / 10  ·  Run reviewed";
            GUILayout.Label(title, heading);
            GUILayout.Label($"{run.hits.Count} goals · {run.duration:0.0}s · {run.distance:0.0} units travelled", detail);

            reviewScroll = GUILayout.BeginScrollView(reviewScroll, GUILayout.ExpandHeight(true));
            if (review != null)
            {
                GUILayout.Label(review.feedback, body);
                GUILayout.Space(18);
                GUILayout.Label("NEXT / " + review.nextLevel.title, body);
                GUILayout.Label(review.nextLevel.description, body);
            }
            else
            {
                GUILayout.Label(status ?? "", body);
            }
            if (!string.IsNullOrEmpty(saveError))
                GUILayout.Label(saveError, detail);
            GUILayout.EndScrollView();

            Action action = Action.None;
            if (!waiting)
            {
                if (review != null && GUILayout.Button("Play generated level  →", button))
                    action = Action.NextLevel;
                if (review == null && GUILayout.Button("Retry local coach", button))
                    action = Action.Retry;
                if (GUILayout.Button("Replay practice", button))
                    action = Action.Practice;
            }
            GUILayout.EndArea();
            return action;
        }

        private void InitStyles()
        {
            if (heading != null)
                return;

            heading = new GUIStyle(GUI.skin.label)
            {
                fontSize = 30,
                fontStyle = FontStyle.Bold,
                wordWrap = true
            };
            heading.normal.textColor = Color.white;
            body = new GUIStyle(GUI.skin.label) { fontSize = 17, wordWrap = true };
            body.normal.textColor = new Color(0.78f, 0.85f, 0.9f);
            detail = new GUIStyle(body) { fontSize = 13 };
            button = new GUIStyle(GUI.skin.button) { fontSize = 16, fixedHeight = 42 };
        }
    }
}
