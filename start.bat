@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY where python >nul 2>&1 && set "PY=python"
if not defined PY if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "PY=%LocalAppData%\Programs\Python\Python312\python.exe"
if not defined PY (
    echo Python не найден. Запустите install.bat
    pause
    exit /b 1
)
%PY% main.py

if %errorlevel% neq 0 (
    echo.
    echo Если приложение не запускается, сначала запустите install.bat
    pause
)
