@echo off
setlocal
title Instalar dependencias do AI-Up
set "PYTHONUTF8=1"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install_ai_up.ps1"
set "install_result=%ERRORLEVEL%"
echo.
if not "%install_result%"=="0" echo Confira a mensagem acima antes de tentar novamente.
echo Pressione uma tecla para fechar.
pause >nul
exit /b %install_result%
