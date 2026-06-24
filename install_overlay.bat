@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "APK=%~dp0overlay-app\app\build\outputs\apk\debug\app-debug.apk"
if not exist "%APK%" (
    echo APK не найден. Сначала запустите build_overlay.bat
    pause
    exit /b 1
)
if exist "%~dp0adb\adb.exe" (
    "%~dp0adb\adb.exe" install -r "%APK%"
) else (
    adb install -r "%APK%"
)
echo.
echo На TV разрешите «Поверх других приложений» для Evo Timer.
pause
