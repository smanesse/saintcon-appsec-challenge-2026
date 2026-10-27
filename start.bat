@echo off
rem Start the SAINTCON AppSec fleet on Windows.
rem
rem   start.bat                       console only (fast)
rem   start.bat fmm dnsm              console + those modules (and their dependencies)
rem   start.bat day1 ^| day2 ^| day3 ^| all   console + that release day's modules
rem   start.bat --build-only all      build images without starting anything
rem
rem Delegates to start.sh via bash so secrets, profiles, and dependency wiring
rem stay identical across platforms. Needs Docker Desktop plus a bash (Git for
rem Windows ships one; WSL works too).
setlocal enabledelayedexpansion
cd /d "%~dp0"

where bash >nul 2>nul
if %ERRORLEVEL%==0 (
  bash ./start.sh %*
  exit /b !ERRORLEVEL!
)

if exist "%ProgramFiles%\Git\bin\bash.exe" (
  "%ProgramFiles%\Git\bin\bash.exe" ./start.sh %*
  exit /b !ERRORLEVEL!
)

echo No 'bash' found on PATH.
echo Install Git for Windows (provides Git Bash) or enable WSL, then re-run start.bat,
echo or run it directly from a Git Bash / WSL shell:  ./start.sh %*
exit /b 1
