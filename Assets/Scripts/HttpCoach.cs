using System;
using System.Collections;
using System.Text;
using UnityEngine.Networking;

namespace CubeCoachGame
{
    internal static class HttpCoach
    {
        internal static IEnumerator Review(string runJson, Action<string> onStatus, Action<string> onReply)
        {
            using var request = new UnityWebRequest("http://127.0.0.1:8765/review", "POST");
            request.uploadHandler = new UploadHandlerRaw(Encoding.UTF8.GetBytes(runJson));
            request.downloadHandler = new DownloadHandlerBuffer();
            request.SetRequestHeader("Content-Type", "application/json");
            request.timeout = 180;
            UnityWebRequestAsyncOperation operation;
            try { operation = request.SendWebRequest(); }
            catch (InvalidOperationException exception)
            {
                onStatus("Local coach request could not start. " + exception.Message);
                yield break;
            }
            yield return operation;
            if (request.result == UnityWebRequest.Result.Success)
                onReply(request.downloadHandler.text);
            else
                onStatus("Local coach unavailable. Start LocalCoach/server.py, then retry. " +
                    request.error + " " + request.downloadHandler.text);
        }

    }
}
