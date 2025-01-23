@echo off
echo Checking if WSL (wsl.exe) is located in C:\Windows\System32...

IF EXIST "C:\Windows\System32\wsl.exe" (
    echo [OK] Found wsl.exe, launching Ubuntu...
    start "Ubuntu Shell" "C:\Windows\System32\wsl.exe" -d Ubuntu -- bash -c "if [ -d myenv ]; then echo 'Activating myenv virtual environment...'; source myenv/bin/activate; else echo 'No ~/myenv folder found, skipping venv activation.'; fi; exec bash"
) ELSE (
    echo [ERROR] wsl.exe is not found in C:\Windows\System32.
    echo Please install WSL from the Microsoft Store or via 'wsl --install'.
    pause
    exit /b
)

pause
