"""Скачивание SDK/Gradle и сборка overlay APK. Запуск: python tools/setup_overlay_build.py"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OVERLAY = ROOT / "overlay-app"
SDK_ROOT = Path(os.environ.get("ANDROID_HOME", Path.home() / "AppData/Local/Android/Sdk"))
TOOLS_ZIP_URLS = [
    "https://dl.google.com/android/repository/commandlinetools-win-11076708_latest.zip",
    "https://mirrors.cloud.tencent.com/AndroidSDK/commandlinetools-win-11076708_latest.zip",
]
GRADLE_WRAPPER_JAR_URLS = [
    "https://github.com/gradle/gradle/raw/v8.5.0/gradle/wrapper/gradle-wrapper.jar",
    "https://raw.githubusercontent.com/gradle/gradle/v8.5.0/gradle/wrapper/gradle-wrapper.jar",
]
GRADLE_DIST_URLS = [
    "https://services.gradle.org/distributions/gradle-8.5-bin.zip",
    "https://github.com/gradle/gradle-distributions/releases/download/v8.5.0/gradle-8.5-bin.zip",
]

LINKS_FILE = ROOT / "OVERLAY_DOWNLOADS.txt"
LOCAL_DOWNLOADS = ROOT / "downloads"
BUILD_CACHE = Path.home() / "AppData" / "Local" / "evo-remote-build"


def find_local_file(*patterns: str) -> Path | None:
    if not LOCAL_DOWNLOADS.is_dir():
        return None
    names = {p.name.lower(): p for p in LOCAL_DOWNLOADS.iterdir() if p.is_file()}
    for pattern in patterns:
        pat = pattern.lower()
        for name, path in names.items():
            if pat in name:
                return path
    return None


def install_jdk_from_downloads() -> bool:
    msi = find_local_file("openjdk", "temurin", ".msi")
    if not msi:
        return False
    log(f"Устанавливаем Java из {msi.name} ...")
    try:
        subprocess.run(
            [
                "msiexec",
                "/i",
                str(msi),
                "/passive",
                "ADDLOCAL=FeatureMain,FeatureEnvironment,FeatureJarFileRunWith,FeatureJavaHome",
            ],
            check=False,
            timeout=600,
        )
    except Exception as exc:
        log(f"msiexec: {exc}")
    return find_java_home() is not None


def extract_cmdline_tools(zip_path: Path) -> None:
    tools = SDK_ROOT / "cmdline-tools" / "latest" / "bin" / "sdkmanager.bat"
    if tools.exists():
        return
    log(f"Распаковка Android SDK из {zip_path.name} ...")
    extract = BUILD_CACHE / "cmdline-tools-extract"
    if extract.exists():
        shutil.rmtree(extract)
    extract.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(extract)
    dest = SDK_ROOT / "cmdline-tools" / "latest"
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)
    src = extract / "cmdline-tools"
    for item in src.iterdir():
        target = dest / item.name
        if item.is_dir():
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)
    log(f"  OK SDK tools: {tools}")


def setup_gradle_from_local() -> None:
    wrapper_dir = OVERLAY / "gradle" / "wrapper"
    wrapper_dir.mkdir(parents=True, exist_ok=True)
    jar_local = find_local_file("gradle-wrapper.jar", "wrapper.jar")
    if jar_local:
        shutil.copy2(jar_local, wrapper_dir / "gradle-wrapper.jar")
        log(f"gradle-wrapper.jar <- {jar_local.name}")

    gradle_zip = find_local_file("gradle-8.5", "gradle-8.5-bin.zip")
    props = wrapper_dir / "gradle-wrapper.properties"
    if gradle_zip:
        BUILD_CACHE.mkdir(parents=True, exist_ok=True)
        staged = BUILD_CACHE / "gradle-8.5-bin.zip"
        if not staged.exists() or staged.stat().st_size != gradle_zip.stat().st_size:
            shutil.copy2(gradle_zip, staged)
        uri = staged.as_posix()
        file_url = f"file\\:///{uri}"
        props.write_text(
            "distributionBase=GRADLE_USER_HOME\n"
            "distributionPath=wrapper/dists\n"
            f"distributionUrl={file_url}\n"
            "zipStoreBase=GRADLE_USER_HOME\n"
            "zipStorePath=wrapper/dists\n",
            encoding="utf-8",
        )
        log(f"Gradle локально: {staged}")


def use_local_downloads() -> bool:
    if not LOCAL_DOWNLOADS.is_dir():
        return False
    files = list(LOCAL_DOWNLOADS.iterdir())
    if not files:
        return False
    log(f"Найдена папка downloads ({len(files)} файлов) — используем локальные файлы.\n")
    setup_gradle_from_local()
    sdk_zip = find_local_file("commandlinetools", "cmdline-tools")
    if sdk_zip:
        extract_cmdline_tools(sdk_zip)
    if find_java_home() is None:
        install_jdk_from_downloads()
    return True


def log(msg: str) -> None:
    text = msg.encode("cp1251", errors="replace").decode("cp1251")
    print(text, flush=True)


def find_java_home() -> Path | None:
    candidates: list[str] = []
    if os.environ.get("JAVA_HOME"):
        candidates.append(os.environ["JAVA_HOME"])
    candidates.extend(
        [
            r"C:\Program Files\Android\Android Studio\jbr",
            r"C:\Program Files\Android\Android Studio\jre",
        ]
    )
    for base in (
        Path(r"C:\Program Files\Eclipse Adoptium"),
        Path(r"C:\Program Files\Java"),
        Path(r"C:\Program Files\Microsoft"),
    ):
        if base.is_dir():
            for child in sorted(base.glob("jdk*"), reverse=True):
                candidates.append(str(child))
    for item in candidates:
        java = Path(item) / "bin" / "java.exe"
        if java.exists():
            return Path(item)
    java = shutil.which("java")
    if java:
        return Path(java).resolve().parent.parent
    return None


def try_install_java_winget() -> bool:
    """Optional: install Temurin JDK 17 via winget."""
    winget = shutil.which("winget")
    if not winget:
        return False
    log("Java не найден. Пробуем установить через winget (Temurin 17) ...")
    try:
        subprocess.run(
            [
                winget,
                "install",
                "-e",
                "--id",
                "EclipseAdoptium.Temurin.17.JDK",
                "--accept-package-agreements",
                "--accept-source-agreements",
            ],
            check=False,
            timeout=600,
        )
    except Exception:
        return False
    return find_java_home() is not None


def ensure_java(env: dict[str, str]) -> None:
    home = find_java_home()
    if home is None and install_jdk_from_downloads():
        home = find_java_home()
    if home is None and try_install_java_winget():
        home = find_java_home()
    if home is None:
        raise RuntimeError(
            "Java JDK 17 не найден.\n"
            "Скачайте: https://adoptium.net/temurin/releases/?version=17\n"
            "Или установите Android Studio.\n"
            f"Все ссылки: {LINKS_FILE}"
        )
    env["JAVA_HOME"] = str(home)
    log(f"Java: {home}")


def download(urls: list[str], dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    for url in urls:
        try:
            log(f"  -> {url}")
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = resp.read()
            if len(data) < 1000:
                raise OSError(f"слишком маленький файл ({len(data)} байт)")
            dest.write_bytes(data)
            log(f"  OK сохранено: {dest} ({len(data)} байт)")
            return
        except Exception as exc:
            errors.append(f"{url}\n    {exc}")
    raise RuntimeError("Не удалось скачать файл. Попробуйте вручную:\n" + "\n".join(errors))


def curl_download(urls: list[str], dest: Path) -> bool:
    curl = shutil.which("curl.exe") or shutil.which("curl")
    if not curl:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    for url in urls:
        try:
            log(f"  curl → {url}")
            subprocess.run(
                [curl, "-L", "--fail", "--retry", "3", "-o", str(dest), url],
                check=True,
                timeout=300,
            )
            if dest.stat().st_size > 1000:
                return True
        except Exception:
            continue
    return False


def ensure_gradle_wrapper() -> None:
    wrapper_dir = OVERLAY / "gradle" / "wrapper"
    wrapper_dir.mkdir(parents=True, exist_ok=True)
    jar = wrapper_dir / "gradle-wrapper.jar"
    if jar.exists() and jar.stat().st_size > 30000:
        return
    local = find_local_file("gradle-wrapper.jar", "wrapper.jar")
    if local:
        shutil.copy2(local, jar)
        log(f"gradle-wrapper.jar <- {local.name}")
        return
    log("Скачиваем gradle-wrapper.jar ...")
    try:
        download(GRADLE_WRAPPER_JAR_URLS, jar)
    except RuntimeError:
        if not curl_download(GRADLE_WRAPPER_JAR_URLS, jar):
            raise


def ensure_gradlew_bat() -> None:
    bat = OVERLAY / "gradlew.bat"
    if bat.exists():
        return
    bat.write_text(
        r"""@rem Gradle wrapper
@if "%DEBUG%"=="" @echo off
set DIR=%~dp0
set APP_BASE_NAME=%~n0
set APP_HOME=%DIR%
@rem Find java.exe
if defined JAVA_HOME goto findJavaFromJavaHome
set JAVA_EXE=java.exe
%JAVA_EXE% -version >NUL 2>&1
if %ERRORLEVEL% equ 0 goto execute
echo ERROR: JAVA_HOME is not set and no 'java' command could be found in your PATH.
exit /b 1
:findJavaFromJavaHome
set JAVA_HOME=%JAVA_HOME:"=%
set JAVA_EXE=%JAVA_HOME%/bin/java.exe
if exist "%JAVA_EXE%" goto execute
echo ERROR: JAVA_HOME is set to an invalid directory: %JAVA_HOME%
exit /b 1
:execute
"%JAVA_EXE%" -jar "%APP_HOME%gradle\wrapper\gradle-wrapper.jar" %*
""",
        encoding="utf-8",
    )


def ensure_sdk() -> Path:
    SDK_ROOT.mkdir(parents=True, exist_ok=True)
    tools = SDK_ROOT / "cmdline-tools" / "latest" / "bin" / "sdkmanager.bat"
    if not tools.exists():
        local = find_local_file("commandlinetools", "cmdline-tools")
        if local:
            extract_cmdline_tools(local)
    if not tools.exists():
        log("Скачиваем Android commandline-tools ...")
        zip_path = ROOT / ".cache" / "cmdline-tools.zip"
        try:
            download(TOOLS_ZIP_URLS, zip_path)
        except RuntimeError:
            if not curl_download(TOOLS_ZIP_URLS, zip_path):
                raise
        extract = ROOT / ".cache" / "cmdline-tools-extract"
        if extract.exists():
            shutil.rmtree(extract)
        extract.mkdir(parents=True)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract)
        dest = SDK_ROOT / "cmdline-tools" / "latest"
        dest.mkdir(parents=True, exist_ok=True)
        src = extract / "cmdline-tools"
        for item in src.iterdir():
            shutil.move(str(item), str(dest / item.name))
        log(f"  OK SDK tools: {tools}")

    sdkmanager = [str(tools), f"--sdk_root={SDK_ROOT}"]
    env = os.environ.copy()
    try:
        ensure_java(env)
    except RuntimeError as exc:
        log(str(exc))
        log("SDK tools скачаны, но для sdkmanager нужна Java.")
        if not (SDK_ROOT / "platforms" / "android-34").exists():
            raise
        return SDK_ROOT
    log("Устанавливаем platform android-34 и build-tools ...")
    subprocess.run(
        sdkmanager + ["--install", "platforms;android-34", "build-tools;34.0.0"],
        input="y\n" * 20,
        text=True,
        check=False,
        env=env,
    )
    # licenses
    proc = subprocess.Popen(
        sdkmanager + ["--licenses"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )
    out, _ = proc.communicate("y\n" * 30)
    if out:
        log(out[-500:])
    return SDK_ROOT


def write_local_properties(sdk: Path) -> None:
    props = OVERLAY / "local.properties"
    # Android Gradle plugin wants sdk.dir with escaped backslashes on Windows
    sdk_dir = str(sdk).replace("\\", "\\\\")
    props.write_text(f"sdk.dir={sdk_dir}\n", encoding="utf-8")


def write_links_file() -> None:
    LINKS_FILE.write_text(
        """# Ручная загрузка (если скрипт не качает)

## 1. Android commandline-tools (Windows)
https://dl.google.com/android/repository/commandlinetools-win-11076708_latest.zip
Зеркало: https://mirrors.cloud.tencent.com/AndroidSDK/commandlinetools-win-11076708_latest.zip

Распакуйте в: %LOCALAPPDATA%\\Android\\Sdk\\cmdline-tools\\latest\\
(внутри должно быть bin\\sdkmanager.bat)

## 2. Gradle 8.5 (если нужен вручную)
https://services.gradle.org/distributions/gradle-8.5-bin.zip
Зеркало: https://github.com/gradle/gradle-distributions/releases/download/v8.5.0/gradle-8.5-bin.zip

## 3. gradle-wrapper.jar → положить в overlay-app\\gradle\\wrapper\\
https://github.com/gradle/gradle/raw/v8.5.0/gradle/wrapper/gradle-wrapper.jar

## 4. Java JDK 17+
https://adoptium.net/temurin/releases/?version=17

## После ручной установки SDK:
cd overlay-app
gradlew.bat assembleDebug
adb install -r app\\build\\outputs\\apk\\debug\\app-debug.apk
""",
        encoding="utf-8",
    )


def build_apk(sdk: Path) -> Path:
    write_local_properties(sdk)
    gradlew = OVERLAY / "gradlew.bat"
    env = os.environ.copy()
    env["ANDROID_HOME"] = str(sdk)
    env["JAVA_TOOL_OPTIONS"] = "-Dfile.encoding=UTF-8"
    ensure_java(env)
    log("Сборка APK (первый раз Gradle тоже скачается, 2–5 мин) ...")
    subprocess.run(
        [str(gradlew), "assembleDebug", "--no-daemon", "--stacktrace"],
        cwd=OVERLAY,
        env=env,
        check=True,
    )
    apk = OVERLAY / "app" / "build" / "outputs" / "apk" / "debug" / "app-debug.apk"
    if not apk.exists():
        raise FileNotFoundError(f"APK не найден: {apk}")
    return apk


def install_apk(apk: Path) -> None:
    adb_candidates = [Path("C:/adb/adb.exe"), Path("adb.exe")]
    adb = next((p for p in adb_candidates if p.exists()), None)
    if adb is None:
        adb = shutil.which("adb")
        if adb:
            adb = Path(adb)
    if not adb:
        log("adb не найден — установите APK вручную:")
        log(f"  adb install -r {apk}")
        return
    log("Установка на TV ...")
    subprocess.run([str(adb), "install", "-r", str(apk)], check=True)


def main() -> int:
    write_links_file()
    log("=== Evo Timer Overlay — сборка ===\n")
    try:
        use_local_downloads()
        ensure_gradlew_bat()
        ensure_gradle_wrapper()
        sdk = ensure_sdk()
        apk = build_apk(sdk)
        log(f"\nOK Готово: {apk}")
        try:
            install_apk(apk)
        except subprocess.CalledProcessError:
            log("Установка не удалась. Подключите TV и выполните install_overlay.bat")
        log(f"\nСсылки для ручной загрузки: {LINKS_FILE}")
        return 0
    except Exception as exc:
        log(f"\nОШИБКА: {exc}")
        log(f"\nОткройте файл со ссылками: {LINKS_FILE}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
