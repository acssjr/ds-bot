@echo off
setlocal

set "PROJECT_DIR=%~dp0"
set "PYTHONW=%PROJECT_DIR%.venv312\Scripts\pythonw.exe"

if not exist "%PYTHONW%" (
    echo Ambiente Python nao encontrado em:
    echo %PYTHONW%
    echo.
    echo Execute primeiro a instalacao descrita no README.md.
    pause
    exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
    "$project = [IO.Path]::GetFullPath('%PROJECT_DIR%');" ^
    "$pythonw = [IO.Path]::GetFullPath('%PYTHONW%');" ^
    "$running = Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'pythonw.exe' -and $_.CommandLine -like '*src.gui.app*' -and $_.ExecutablePath -like ($project + '*') };" ^
    "if (-not $running) { Start-Process -FilePath $pythonw -ArgumentList '-m','src.gui.app' -WorkingDirectory $project -WindowStyle Hidden }"
exit /b 0
