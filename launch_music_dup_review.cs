using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

internal static class MusicDupReviewLauncher
{
    [STAThread]
    private static int Main()
    {
        string appDir = AppDomain.CurrentDomain.BaseDirectory;
        string pythonw = Path.Combine(appDir, ".venv", "Scripts", "pythonw.exe");
        string python = Path.Combine(appDir, ".venv", "Scripts", "python.exe");
        string interpreter = File.Exists(pythonw) ? pythonw : python;

        if (!File.Exists(interpreter))
        {
            MessageBox.Show(
                "Python environment not found. Expected .venv\\Scripts\\pythonw.exe beside launcher.",
                "Music Duplicate Review",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error
            );
            return 1;
        }

        try
        {
            ProcessStartInfo startInfo = new ProcessStartInfo
            {
                FileName = interpreter,
                Arguments = "-m pyside_app.main",
                WorkingDirectory = appDir,
                UseShellExecute = false,
                CreateNoWindow = true
            };
            Process.Start(startInfo);
            return 0;
        }
        catch (Exception ex)
        {
            MessageBox.Show(ex.Message, "Music Duplicate Review", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }
}
