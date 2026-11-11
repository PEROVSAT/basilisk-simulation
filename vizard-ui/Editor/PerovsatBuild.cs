using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEngine;

public static class PerovsatBuild
{
    [MenuItem("PEROVSAT/Build Windows Viewer")]
    public static void BuildWindows()
    {
        string output = Path.GetFullPath("Builds/Perovsat/Vizard.exe");
        string[] arguments = Environment.GetCommandLineArgs();
        for (int index = 0; index < arguments.Length - 1; index++)
            if (arguments[index] == "-perovsatOutput")
                output = Path.GetFullPath(arguments[index + 1]);
        string[] scenes = { FindScene("VizardStartupScene"), FindScene("VizardMainScene") };
        if (Resources.Load<Font>("PerovsatTelemetry/Barlow-Regular") == null
            || Resources.Load<Font>("PerovsatTelemetry/Barlow-SemiBold") == null)
            throw new InvalidOperationException("Import the bundled Barlow fonts before building.");
        Directory.CreateDirectory(Path.GetDirectoryName(output));
        BuildReport report = BuildPipeline.BuildPlayer(new BuildPlayerOptions
        {
            scenes = scenes,
            locationPathName = output,
            target = BuildTarget.StandaloneWindows64,
            options = BuildOptions.None
        });
        if (report.summary.result != BuildResult.Succeeded)
            throw new InvalidOperationException("Vizard build failed: " + report.summary.result);
        Debug.Log("PEROVSAT viewer built: " + output);
    }

    private static string FindScene(string name)
    {
        string[] paths = AssetDatabase.FindAssets(name + " t:Scene")
            .Select(AssetDatabase.GUIDToAssetPath)
            .Where(path => Path.GetFileNameWithoutExtension(path) == name).ToArray();
        if (paths.Length != 1)
            throw new InvalidOperationException("Expected exactly one scene named " + name);
        return paths[0];
    }
}
