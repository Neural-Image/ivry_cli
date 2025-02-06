@echo off
REM Step 1: Enable WSL and Virtualization Features
echo Enabling WSL and Virtualization Features...
dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart

echo Restart your computer to complete this step.
pause

REM Step 2: Install Ubuntu
echo Installing Ubuntu 22.04...

REM Check if WSL is already installed
wsl --install -d Ubuntu-22.04

REM Inform user to check installation
echo Installation complete! You may need to manually configure Ubuntu after installation.
pause
