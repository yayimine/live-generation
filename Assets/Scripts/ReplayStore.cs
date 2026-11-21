using System.IO;
using UnityEngine;

namespace CubeCoachGame
{
    internal static class ReplayStore
    {
        internal static string Save(Run run)
        {
            var directory = Path.Combine(Application.persistentDataPath, "Runs");
            Directory.CreateDirectory(directory);
            var path = Path.Combine(directory, run.id + ".json");
            File.WriteAllText(path, JsonUtility.ToJson(run, true));
            return path;
        }

        internal static void SaveReview(string replayPath, Review review)
        {
            File.WriteAllText(Path.ChangeExtension(replayPath, ".review.json"),
                JsonUtility.ToJson(review, true));
        }
    }
}
