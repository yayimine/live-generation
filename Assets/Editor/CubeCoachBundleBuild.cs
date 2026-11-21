using System.Diagnostics;
using System.IO;
using UnityEditor;
using UnityEditor.Build;
using UnityEditor.Build.Reporting;
using UnityEngine;
using Debug = UnityEngine.Debug;

internal sealed class CubeCoachBundleBuild : IPostprocessBuildWithReport
{
    public int callbackOrder => int.MaxValue;

    public void OnPostprocessBuild(BuildReport report)
    {
        if (report.summary.platform != BuildTarget.StandaloneOSX)
            return;

        var project = Path.GetDirectoryName(Application.dataPath);
        var source = Path.Combine(project, "LocalCoach", "macos-runtime");
        var app = Path.GetFullPath(report.summary.outputPath);
        var target = Path.Combine(app, "Contents", "Resources", "CubeCoachRuntime");

        // Rebuilding into the same path should never keep a stale model or adapter.
        var hadBundle = Directory.Exists(target);
        if (hadBundle)
            Directory.Delete(target, true);
        if (!Directory.Exists(source))
        {
            if (hadBundle)
                Sign(app);
            Debug.Log("Cube Coach runtime is unstaged. See README-CubeCoach.md for bundled builds.");
            return;
        }

        if (Application.platform != RuntimePlatform.OSXEditor)
            throw new BuildFailedException("Build the staged Cube Coach runtime from macOS.");

        foreach (var file in new[] { "python/bin/python3.12", "server.py", "model/config.json",
                                    "adapter/adapter_config.json", "adapter/adapter_model.safetensors" })
        {
            if (!File.Exists(Path.Combine(source, file)))
                throw new BuildFailedException("Incomplete Cube Coach runtime. Missing " + file);
        }

        Run("/usr/bin/ditto", Quote(source) + " " + Quote(target));
        Sign(app);
        Debug.Log("Packaged the Cube Coach runtime, model, and adapter into " + app);
    }

    private static void Sign(string app)
    {
        Run("/usr/bin/codesign", "--force --sign - " + Quote(app));
        Run("/usr/bin/codesign", "--verify " + Quote(app));
    }

    private static string Quote(string path) =>
        "\"" + path.Replace("\\", "\\\\").Replace("\"", "\\\"") + "\"";

    private static void Run(string tool, string arguments)
    {
        using var child = Process.Start(new ProcessStartInfo(tool, arguments)
        {
            UseShellExecute = false,
            RedirectStandardError = true
        });
        var output = child.StandardError.ReadToEnd();
        child.WaitForExit();
        if (child.ExitCode != 0)
            throw new BuildFailedException(tool + " failed. " + output);
    }
}
