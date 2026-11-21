using System;
using System.Collections;
using System.Collections.Concurrent;
using System.Diagnostics;
using System.IO;
using System.Threading.Tasks;
using UnityEngine;
using Debug = UnityEngine.Debug;

namespace CubeCoachGame
{
    internal sealed class BundledCoach : IDisposable
    {
        internal static string RuntimePath =>
            Path.Combine(Application.dataPath, "Resources", "CubeCoachRuntime");

        internal static bool IsInstalled =>
            !Application.isEditor && Application.platform == RuntimePlatform.OSXPlayer &&
            Directory.Exists(RuntimePath);

        private Process process;
        private ConcurrentQueue<string> replies;
        private bool ready;

        [Serializable]
        private sealed class Message
        {
            public bool ready;
            public string error;
        }

        internal void WarmUp()
        {
            if (process != null && !process.HasExited)
                return;

            Dispose();
            var incoming = new ConcurrentQueue<string>();
            var info = new ProcessStartInfo
            {
                FileName = Path.Combine(RuntimePath, "python/bin/python3.12"),
                Arguments = "-sBu server.py --stdio --model model --adapter adapter",
                WorkingDirectory = RuntimePath,
                UseShellExecute = false,
                RedirectStandardInput = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true
            };
            info.EnvironmentVariables["PYTHONPATH"] = Path.Combine(RuntimePath, "packages");
            info.EnvironmentVariables["HF_HUB_OFFLINE"] = "1";
            info.EnvironmentVariables["TRANSFORMERS_OFFLINE"] = "1";
            info.EnvironmentVariables.Remove("PYTHONHOME");
            var child = new Process { StartInfo = info };
            child.OutputDataReceived += (_, args) =>
            {
                if (args.Data != null)
                    incoming.Enqueue(args.Data);
            };
            child.ErrorDataReceived += (_, args) =>
            {
                if (!string.IsNullOrWhiteSpace(args.Data))
                    Debug.Log("Cube Coach: " + args.Data);
            };
            process = child;
            replies = incoming;
            try
            {
                child.Start();
                child.StandardInput.AutoFlush = true;
                child.BeginOutputReadLine();
                child.BeginErrorReadLine();
            }
            catch
            {
                Dispose();
                throw;
            }
        }

        internal IEnumerator Review(string runJson, Action<string> onStatus, Action<string> onReply)
        {
            try
            {
                WarmUp();
            }
            catch (Exception exception)
            {
                onStatus("Could not start the bundled coach. " + exception.Message);
                yield break;
            }

            if (!ready)
            {
                onStatus("Loading the local model…");
                yield return WaitForLine(120, line =>
                {
                    ready = JsonUtility.FromJson<Message>(line)?.ready == true;
                }, onStatus);
                if (!ready)
                {
                    if (process != null)
                    {
                        onStatus("The bundled coach did not send its startup message.");
                        Dispose();
                    }
                    yield break;
                }
            }

            onStatus("Local coach is reviewing your run…");
            Task write;
            try
            {
                write = process.StandardInput.WriteLineAsync(runJson);
            }
            catch (Exception exception)
            {
                onStatus("The bundled coach could not receive the run. " + exception.Message);
                Dispose();
                yield break;
            }
            var deadline = Time.realtimeSinceStartup + 15;
            while (!write.IsCompleted && !process.HasExited && Time.realtimeSinceStartup < deadline)
                yield return null;
            if (!write.IsCompleted || write.IsFaulted || process.HasExited)
            {
                onStatus("The bundled coach could not receive the run. Retry to restart it.");
                Dispose();
                yield break;
            }

            yield return WaitForLine(180, line =>
            {
                var error = JsonUtility.FromJson<Message>(line)?.error;
                if (string.IsNullOrEmpty(error))
                    onReply(line);
                else
                    onStatus("Coach could not review the run. " + error);
            }, onStatus);
        }

        private IEnumerator WaitForLine(float seconds, Action<string> onLine, Action<string> onStatus)
        {
            var deadline = Time.realtimeSinceStartup + seconds;
            while (Time.realtimeSinceStartup < deadline)
            {
                if (replies.TryDequeue(out var line))
                {
                    try
                    {
                        onLine(line);
                    }
                    catch (Exception exception)
                    {
                        onStatus("Invalid response from the bundled coach. " + exception.Message);
                        Dispose();
                    }
                    yield break;
                }
                if (process.HasExited)
                    break;
                yield return null;
            }
            onStatus(process.HasExited
                ? "The bundled coach exited. See the player log for details."
                : "The bundled coach timed out. Retry to restart it.");
            Dispose();
        }

        public void Dispose()
        {
            var child = process;
            process = null;
            ready = false;
            if (child == null)
                return;
            try
            {
                if (!child.HasExited)
                    child.Kill();
            }
            catch (InvalidOperationException)
            {
                // The process already exited or failed to start.
            }
            finally
            {
                child.Dispose();
            }
        }
    }
}
