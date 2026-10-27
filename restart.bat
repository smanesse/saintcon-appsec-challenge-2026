@echo off
rem Restart the SAINTCON AppSec fleet on Windows: stop everything, then start.
rem
rem   restart.bat                       console only (fast)
rem   restart.bat fmm dnsm              console + those modules (and their dependencies)
rem   restart.bat day1 ^| day2 ^| day3 ^| all   console + that release day's modules
rem   restart.bat --build-only all      build images without starting anything
rem
rem Delegates to restart.sh via bash so secrets, profiles, and dependency wiring
rem stay identical across platforms. Needs Docker Desktop plus a bash (Git for
rem Windows ships one; WSL works too).
setlocal enabledelayedexpansion
cd /d "%~dp0"

where bash >nul 2>nul
if %ERRORLEVEL%==0 (
  bash ./restart.sh %*
  exit /b !ERRORLEVEL!
)

if exist "%ProgramFiles%\Git\bin\bash.exe" (
  "%ProgramFiles%\Git\bin\bash.exe" ./restart.sh %*
  exit /b !ERRORLEVEL!
)

echo No 'bash' found on PATH.
echo Install Git for Windows (provides Git Bash) or enable WSL, then re-run restart.bat,
echo or run it directly from a Git Bash / WSL shell:  ./restart.sh %*
exit /b 1
