@echo off
setlocal
title AI-Up
set "PYTHONUTF8=1"
set "demo_flag="
if /i "%~1"=="--demo" set "demo_flag=-Demo"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_ai_up.ps1" -Desktop %demo_flag%
if errorlevel 1 (
    echo.
    echo Confira a mensagem acima e pressione uma tecla para fechar.
    pause >nul
    exit /b 1
)
