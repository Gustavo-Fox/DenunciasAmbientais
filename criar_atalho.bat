@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\Denuncias Ambientais.lnk'); $s.TargetPath='%~dp0iniciar.bat'; $s.WorkingDirectory='%~dp0'; $s.IconLocation='%~dp0icone.ico'; $s.WindowStyle=7; $s.Description='Sistema de Denuncias Ambientais'; $s.Save()"
if errorlevel 1 (
  echo Nao foi possivel criar o atalho.
  pause
  exit /b 1
)
echo Atalho "Denuncias Ambientais" criado na area de trabalho.
pause
