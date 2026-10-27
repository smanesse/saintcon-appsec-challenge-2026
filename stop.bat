@echo off
rem Stop the whole SAINTCON AppSec fleet on Windows.
rem
rem   stop.bat            stop everything
rem   stop.bat -v         also remove named volumes (passes flags through)
rem
rem Delegates to stop.sh via bash so behavior stays identical across platforms.
rem Needs Docker Desktop plus a bash (Git for Windows ships one; WSL works too).
setlocal enabledelayedexpansion
cd /d "%~dp0"

where bash >nul 2>nul
if %ERRORLEVEL%==0 (
  bash ./stop.sh %*
  exit /b !ERRORLEVEL!
)

if exist "%ProgramFiles%\Git\bin\bash.exe" (
  "%ProgramFiles%\Git\bin\bash.exe" ./stop.sh %*
  exit /b !ERRORLEVEL!
)

echo No 'bash' found on PATH.
echo Install Git for Windows (provides Git Bash) or enable WSL, then re-run stop.bat,
echo or run it directly from a Git Bash / WSL shell:  ./stop.sh %*
exit /b 1
