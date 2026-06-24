# Control Center

Программа для клуба: пульт телевизора, таймер сессии, несколько TV сразу, таймер в углу экрана (даже когда включена PS или HDMI).

Тестировали на **Haier MatrixTV FR** (Google TV). TV и компьютер должны быть в одной сети.

## С чего начать

1. Запусти **`install.bat`** один раз (скачает ADB и библиотеки Python).
2. Запусти **`start.bat`**.
3. На телевизоре включи отладку по Wi‑Fi, в программе введи IP и нажми «Подключиться».

Если нужен таймер в правом верхнем углу TV:

1. **`build_overlay.bat`** (собрать APK, нужна Java 17)
2. **`install_overlay.bat`** (поставить APK на TV)

## Что качает install.bat

Скрипт сам ставит Python-пакеты и **ADB** (platform-tools).

ADB попадает в `C:\adb\` или в `%LOCALAPPDATA%\evo-remote\platform-tools\`.

Ссылка, если качать руками:  
https://dl.google.com/android/repository/platform-tools-latest-windows.zip  
(можно положить zip в папку `downloads\` и снова запустить install.bat)

### Python-пакеты (requirements.txt)

| Пакет | Для чего |
|-------|----------|
| customtkinter | Окно программы |
| adb-shell | Запасной вариант ADB |
| cryptography | Ключи для ADB |
| Pillow | Скриншоты и картинка с экрана TV |
| psutil | Информация о компьютере |

### Python, если его нет

- https://www.python.org/downloads/ (версия 3.10 или новее)
- или: `winget install Python.Python.3.12`

При установке поставь галочку **Add python.exe to PATH**.

## Что качаем для таймера на TV (build_overlay.bat)

Скрипт сам пробует скачать всё нужное. Если Google не открывается, кидай файлы в **`downloads\`** (подробнее в `downloads/README.txt`).

| Что | Ссылка | Зеркало |
|-----|--------|---------|
| Java JDK 17 (Temurin) | https://adoptium.net/temurin/releases/?version=17 | |
| Android commandline-tools | https://dl.google.com/android/repository/commandlinetools-win-11076708_latest.zip | https://mirrors.cloud.tencent.com/AndroidSDK/commandlinetools-win-11076708_latest.zip |
| Gradle 8.5 | https://services.gradle.org/distributions/gradle-8.5-bin.zip | https://github.com/gradle/gradle-distributions/releases/download/v8.5.0/gradle-8.5-bin.zip |
| gradle-wrapper.jar | https://github.com/gradle/gradle/raw/v8.5.0/gradle/wrapper/gradle-wrapper.jar | https://raw.githubusercontent.com/gradle/gradle/v8.5.0/gradle/wrapper/gradle-wrapper.jar |

Куда класть руками:

- commandline-tools → `%LOCALAPPDATA%\Android\Sdk\cmdline-tools\latest\`
- gradle-wrapper.jar → `overlay-app\gradle\wrapper\`
- JDK → установить .msi и перезапустить build_overlay.bat

Ещё ссылки лежат в **`OVERLAY_DOWNLOADS.txt`**.

## По желанию

| Программа | Зачем |
|-----------|--------|
| [Scrcpy](https://github.com/Genymobile/scrcpy/releases) | Удобное зеркало экрана TV |
| [Android Studio](https://developer.android.com/studio) | Если не хочешь отдельно ставить Java и SDK |

Scrcpy можно положить в `tools\scrcpy\scrcpy.exe`.

## Bat-файлы

| Файл | Что делает |
|------|------------|
| install.bat | Ставит ADB и Python-библиотеки |
| setup.bat | То же самое |
| start.bat | Запуск программы |
| build_overlay.bat | Сборка APK таймера |
| install_overlay.bat | Установка APK на TV |

## Что умеет программа

- **Обзор** - список TV, статус, клик по TV открывает таймер и пульт
- **Клуб · Таймер** - обратный отсчёт, время можно ввести (60, 90:00, 1:30:00)
- **Пульт TV** - стрелки, громкость, вкл/выкл, приложения, тачпад
- **Система TV** - экран на ПК, терминал, файлы, список приложений
- **Компьютер** - выключить, усыпить, заблокировать этот ПК
- **Устройства** - разбудить другие ПК по сети (Wake-on-LAN)

У каждого TV свой IP, свой таймер, порт ADB обычно **5555**.

## Как подключить TV (Haier / Google TV)

1. Первый раз лучше через Wi‑Fi: `adb pair`, потом `adb connect`.
2. На TV: О телевизоре → 7 раз «Номер сборки» → Для разработчиков → отладка.
3. Включи «Отладка по Wi‑Fi», запиши IP.
4. На ПК:

```text
adb connect 192.168.x.x:5555
adb tcpip 5555
adb connect 192.168.x.x:5555
```

Потом можно работать по обычной LAN, если PC и TV в одной подсети.

На TV один раз разреши Evo Timer «Поверх других приложений» (для таймера в углу).

## Файлы в проекте

```text
evo-remote/
  main.py                 - главное окно
  adb_client.py           - работа с TV через ADB
  club_timer.py           - таймер
  tv_overlay.py           - таймер поверх экрана
  tv_registry.py          - несколько TV
  overlay-app/            - Android-приложение для углового таймера
  tools/                  - скрипты установки и сборки
  downloads/              - сюда кладём zip для офлайн-установки
  install.bat / start.bat
```

Настройки программы: `%USERPROFILE%\.evo-remote\config.json`

## GitHub

https://github.com/Holow13/evo-remote

```text
git clone git@github.com:Holow13/evo-remote.git
cd evo-remote
install.bat
start.bat
```
