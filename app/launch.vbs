' Starts the reader server (app/server.py) without a console window and opens it in the browser.
Set fso = CreateObject("Scripting.FileSystemObject")
app = fso.GetParentFolderName(WScript.ScriptFullName)
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = fso.GetParentFolderName(app)
sh.Run "pythonw """ & app & "\server.py""", 0, False
