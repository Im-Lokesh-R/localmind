@echo off
REM ============================================================
REM  LocalMind - one-click setup and launch for Windows
REM  Just double-click this file. First run installs everything
REM  (Python, packages, Ollama, an AI model). Later runs start
REM  instantly.
REM ============================================================
setlocal EnableExtensions
title LocalMind
cd /d "%~dp0"
chcp 65001 >nul

set "PY="

REM --- 1. find an existing Python 3.10+ -------------------------
call :trypy py -3
if not defined PY call :trypy python
if not defined PY call :trypy "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not defined PY call :trypy "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"

REM --- 2. install Python if missing -----------------------------
if not defined PY (
    echo.
    echo ==^> Python not found - installing Python 3.12 ...
    where winget >nul 2>&1
    if not errorlevel 1 (
        winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
    )
    call :trypy "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
)
if not defined PY (
    echo     downloading Python installer from python.org ...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol='Tls12'; Invoke-WebRequest -UseBasicParsing 'https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe' -OutFile \"$env:TEMP\python-installer.exe\""
    "%TEMP%\python-installer.exe" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_pip=1
    call :trypy "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
)
if not defined PY (
    echo.
    echo [ERROR] Could not install Python automatically.
    echo         Install it from https://www.python.org/downloads/ ^(tick "Add to PATH"^)
    echo         and double-click this file again.
    pause
    exit /b 1
)

REM --- 3. hand over to the Python bootstrapper ------------------
%PY% "%~dp0bootstrap.py" %*
if errorlevel 1 (
    echo.
    echo LocalMind stopped with an error. See the messages above.
    pause
)
exit /b

REM ---------------------------------------------------------------
REM :trypy <python command...>  -> sets PY if it is Python 3.10+
:trypy
%* -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if not errorlevel 1 set "PY=%*"
exit /b
