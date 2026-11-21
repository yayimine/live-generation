using System;
using System.Collections;
using UnityEngine;
using UnityEngine.InputSystem;

namespace CubeCoachGame
{
    public class CubeCoach : MonoBehaviour
    {
        private enum Phase { Playing, Reviewing, Results }

        private ArenaView arena;
        private RunSession session;
        private BundledCoach bundledCoach;
        private Review review;
        private Phase phase;
        private int stage = 1;
        private string status;
        private string savedPath;
        private string saveError;
        private readonly CoachHud hud = new();

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        private static void Boot()
        {
            if (FindFirstObjectByType<CubeCoach>() == null)
                new GameObject("Cube Coach").AddComponent<CubeCoach>();
        }

        private void Start()
        {
            Application.runInBackground = true;
            arena = new ArenaView(transform);
            StartLevel(ArenaRules.Practice());
            if (!BundledCoach.IsInstalled)
                return;

            bundledCoach = new BundledCoach();
            try { bundledCoach.WarmUp(); }
            catch (Exception exception) { Debug.LogWarning(exception.Message); }
        }

        private void StartLevel(Level level)
        {
            session = new RunSession(level);
            arena.ShowLevel(level);
            review = null;
            status = null;
            savedPath = null;
            saveError = null;
            phase = Phase.Playing;
        }

        private void Update()
        {
            if (session == null || phase != Phase.Playing)
                return;

            var keyboard = Application.isFocused ? Keyboard.current : null;
            int mask = 0;
            if (keyboard != null)
            {
                if (keyboard.wKey.isPressed) mask |= RunSession.Up;
                if (keyboard.aKey.isPressed) mask |= RunSession.Left;
                if (keyboard.sKey.isPressed) mask |= RunSession.Down;
                if (keyboard.dKey.isPressed) mask |= RunSession.Right;
            }

            session.Step(mask, Time.deltaTime, keyboard?.enterKey.wasPressedThisFrame == true);
            arena.Draw(session);
            if (session.Finished)
                FinishRun();
        }

        private void OnApplicationFocus(bool focused)
        {
            if (!focused)
                session?.ReleaseInput();
        }

        private void FinishRun()
        {
            try
            {
                savedPath = ReplayStore.Save(session.Replay);
                Debug.Log("Cube Coach replay: " + savedPath);
            }
            catch (Exception exception)
            {
                saveError = "Could not save replay. " + exception.Message;
            }
            StartCoroutine(AskCoach());
        }

        private IEnumerator AskCoach()
        {
            phase = Phase.Reviewing;
            status = "Local coach is reviewing your run…";
            string json = JsonUtility.ToJson(session.Replay);
            if (bundledCoach != null)
                yield return bundledCoach.Review(json, SetStatus, AcceptReview);
            else
                yield return HttpCoach.Review(json, SetStatus, AcceptReview);
            phase = Phase.Results;
        }

        private void SetStatus(string message) => status = message;

        private void AcceptReview(string json)
        {
            try
            {
                var result = JsonUtility.FromJson<Review>(json);
                if (!Valid(result))
                {
                    status = "Coach returned an invalid rating or level.";
                    return;
                }
                review = result;
            }
            catch (Exception exception)
            {
                status = "Coach response could not be used. " + exception.Message;
                return;
            }

            if (savedPath == null)
                return;

            try { ReplayStore.SaveReview(savedPath, review); }
            catch (Exception exception) { saveError = "Could not save review. " + exception.Message; }
        }

        public static bool Valid(Review result) => ArenaRules.IsValidReview(result);

        private void OnGUI()
        {
            if (session == null)
                return;

            var action = hud.Draw(session, stage, phase == Phase.Reviewing, review, status, saveError);
            switch (action)
            {
                case CoachHud.Action.NextLevel:
                    stage++;
                    StartLevel(review.nextLevel);
                    break;
                case CoachHud.Action.Retry:
                    StartCoroutine(AskCoach());
                    break;
                case CoachHud.Action.Practice:
                    stage = 1;
                    StartLevel(ArenaRules.Practice());
                    break;
            }
        }

        private void OnDestroy()
        {
            bundledCoach?.Dispose();
            arena?.Dispose();
        }
    }
}
