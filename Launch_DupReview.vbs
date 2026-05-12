Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
appDir = fso.GetParentFolderName(WScript.ScriptFullName)
cmd = """" & appDir & "\.venv\Scripts\pythonw.exe"" """ & appDir & "\dup_review_gui.py"""
shell.CurrentDirectory = appDir
shell.Run cmd, 0, False
