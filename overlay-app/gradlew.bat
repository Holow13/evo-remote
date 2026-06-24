@rem
@rem Copyright 2015 the original author or authors.
@rem
@if "%DEBUG%"=="" @echo off

set DIR=%~dp0
if "%DIR%"=="" set DIR=.
set APP_BASE_NAME=%~n0
set APP_HOME=%DIR%

@rem Find java.exe
if defined JAVA_HOME goto findJavaFromJavaHome
set JAVA_EXE=java.exe
%JAVA_EXE% -version >NUL 2>&1
if %ERRORLEVEL% equ 0 goto execute
echo.
echo ERROR: JAVA_HOME is not set and no 'java' command could be found in your PATH.
echo.
goto fail

:findJavaFromJavaHome
set JAVA_HOME=%JAVA_HOME:"=%
set JAVA_EXE=%JAVA_HOME%/bin/java.exe
if exist "%JAVA_EXE%" goto execute
echo.
echo ERROR: JAVA_HOME is set to an invalid directory: %JAVA_HOME%
echo.
goto fail

:execute
set CLASSPATH=%APP_HOME%gradle\wrapper\gradle-wrapper.jar
"%JAVA_EXE%" %DEFAULT_JVM_OPTS% %JAVA_OPTS% %GRADLE_OPTS% "-Dorg.gradle.appname=%APP_BASE_NAME%" -classpath "%CLASSPATH%" org.gradle.wrapper.GradleWrapperMain %*
goto end

:fail
exit /b 1

:end
if %ERRORLEVEL% equ 0 goto mainEnd
exit /b 1
:mainEnd
