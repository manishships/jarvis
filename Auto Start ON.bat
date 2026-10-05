@echo off
cd /d "%~dp0"
powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Startup')+'\JARVIS.lnk'); $s.TargetPath='%~dp0.venv\Scripts\pythonw.exe'; $s.Arguments='jarvis.py --hud'; $s.WorkingDirectory='%~dp0'; $s.Save()"
echo Ho gaya! Ab laptop on hote hi JARVIS apne aap chalu ho jayega.
pause
