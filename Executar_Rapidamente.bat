@echo off
title Sistema de Denuncias - Servidor
cd /d "%~dp0"

echo Iniciando o sistema...

:: Abre o navegador em segundo plano apos 2 segundos
start "" cmd /c "timeout /t 2 /nobreak >nul && start http://127.0.0.1:5000"

:: Inicia o servidor Flask (mantem o terminal aberto)
python app.py

pause