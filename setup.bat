@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo setup.bat перенаправляет на полную установку...
echo.
call "%~dp0install.bat"
