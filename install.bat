@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo   Control Center — полная установка
echo   ADB + Python + зависимости
echo ========================================
echo.

set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY where python >nul 2>&1 && set "PY=python"
if not defined PY if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "PY=%LocalAppData%\Programs\Python\Python312\python.exe"
if not defined PY if exist "%LocalAppData%\Programs\Python\Python311\python.exe" set "PY=%LocalAppData%\Programs\Python\Python311\python.exe"

if not defined PY (
    echo Python 3.10+ не найден.
    echo.
    echo Установите с https://www.python.org/downloads/
    echo   ^(галочка "Add python.exe to PATH"^)
    echo.
    echo Или через winget:
    echo   winget install Python.Python.3.12
    echo.
    pause
    exit /b 1
)

echo Python: %PY%
echo.

"%PY%" "%~dp0tools\setup_environment.py"
set "ERR=%errorlevel%"

if %ERR% neq 0 (
    echo.
    echo Установка завершилась с ошибкой.
    echo Без интернета положите platform-tools zip в downloads\
    echo См. downloads\README.txt
    pause
    exit /b %ERR%
)

echo.
echo Готово! Запускайте start.bat
echo.
pause
exit /b 0
