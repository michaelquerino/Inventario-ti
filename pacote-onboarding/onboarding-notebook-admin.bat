@echo off
setlocal EnableExtensions
cd /d "%~dp0"

net session >nul 2>&1
if errorlevel 1 (
    echo Solicitando permissao de administrador...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

echo ======================================
echo   Onboarding do Agente Manual
echo ======================================
echo.
echo Execute este arquivo na mesma pasta de Agente_manual.exe.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0onboarding-notebook.ps1"

echo.
pause
