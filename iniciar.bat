@echo off
title Denuncias Ambientais
cd /d "%~dp0"
set PY=python
python --version >nul 2>nul || set PY=py
%PY% --version >nul 2>nul || (
  echo Python nao encontrado. Instale em python.org marcando "Add Python to PATH".
  pause
  exit /b 1
)
%PY% -c "import flask" >nul 2>nul || %PY% -m pip install -r requirements.txt
echo Iniciando o sistema. Mantenha esta janela aberta (pode minimizar); para encerrar, feche-a.
%PY% app.py
if errorlevel 1 pause
