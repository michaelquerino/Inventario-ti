@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\Admin\inventario-empresarial\scripts\frontend-watchdog.ps1" -RepoRoot "C:\Users\Admin\inventario-empresarial" -NodeExe "C:\Program Files\nodejs\node.exe" -ApiBaseUrl ""
