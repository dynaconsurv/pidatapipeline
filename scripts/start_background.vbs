' AVEVA PI to Oracle ERP Cloud Data Pipeline - Silent Background Runner
' This script starts python run.py completely invisibly without showing any CMD window.

Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

' Get project root directory (parent of scripts folder)
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
projectDir = fso.GetParentFolderName(scriptDir)

' Execute python run.py silently in the background (0 = hide window, false = don't wait)
WshShell.CurrentDirectory = projectDir
WshShell.Run "python run.py", 0, False
