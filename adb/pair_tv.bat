@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo   ADB - сопряжение с Haier / Google TV
echo ============================================
echo.
echo НА TV (не закрывай экран):
echo   Для разработчиков -^> Беспроводная отладка
echo   -^> Сопряжение с кодом
echo.
echo Введи данные С ЭКРАНА TV:
echo.

set /p TV_IP="IP TV (напр. 192.168.2.68): "
set /p PAIR_PORT="Порт СОПРЯЖЕНИЯ (pair): "
set /p PAIR_CODE="6-значный код: "

echo.
echo [1/4] Сброс ADB...
adb kill-server >nul 2>&1
adb start-server

echo [2/4] Сопряжение...
adb pair %TV_IP%:%PAIR_PORT% %PAIR_CODE%
if errorlevel 1 (
    echo.
    echo ОШИБКА сопряжения. Получи НОВЫЙ код на TV и запусти скрипт снова.
    pause
    exit /b 1
)

echo.
echo На TV открой главный экран "Беспроводная отладка"
echo (НЕ экран сопряжения) - там другой порт!
echo.
set /p CONN_PORT="Порт ПОДКЛЮЧЕНИЯ с главного экрана: "

echo [3/4] Подключение...
adb disconnect %TV_IP% >nul 2>&1
adb connect %TV_IP%:%CONN_PORT%
timeout /t 2 >nul
adb devices

echo.
echo Статус должен быть "device", НЕ "offline"!
echo Если offline - на TV: Отменить авторизации отладки, pair заново.
echo.
set /p GO="Порт показывает device? (y/n): "
if /i not "%GO%"=="y" (
    echo Прервано. Сначала добейся статуса device.
    pause
    exit /b 1
)

echo [4/4] Переключение на порт 5555...
adb -s %TV_IP%:%CONN_PORT% tcpip 5555
timeout /t 2 >nul
adb disconnect %TV_IP%:%CONN_PORT% >nul 2>&1
adb connect %TV_IP%:5555
timeout /t 2 >nul

echo.
echo === Итог ===
adb devices
echo.
echo Control Center: IP=%TV_IP%  Порт=5555
pause
