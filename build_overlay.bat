@echo off
chcp 65001 >nul
cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 (
    echo Python не найден. Установите Python 3.10+ с python.org
    pause
    exit /b 1
)

python "%~dp0tools\setup_overlay_build.py"
set ERR=%ERRORLEVEL%
echo.
if %ERR% neq 0 (
    echo Если скачивание не работает — откройте OVERLAY_DOWNLOADS.txt
    echo там прямые ссылки на все файлы.
)
pause
exit /b %ERR%
