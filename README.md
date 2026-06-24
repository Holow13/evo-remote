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

## Порты ADB: что мы делали на Haier MatrixTV

На Google TV (наш Haier) **не один порт, а три разных**. Это важно, иначе кажется что «ничего не работает».

### Три порта, не путай

| Порт | Для чего | Пример |
|------|----------|--------|
| **Порт сопряжения** | Только команда `adb pair` + 6-значный код с TV | `192.168.2.68:40323` |
| **Порт подключения** | Временный `adb connect` сразу после pair | `192.168.2.68:39119` |
| **5555** | Постоянный порт для клуба и Control Center | `192.168.2.72:5555` |

Порты сопряжения и подключения **каждый раз новые** (типа 40323, 39119). Они видны на TV в «Беспроводная отладка».  
**5555** мы включаем сами командой `tcpip 5555` и дальше в программе всегда пишем его.

### Почему сначала нужен Wi‑Fi

На Haier с **LAN-кабелем** переключатель «Беспроводная отладка» часто **сразу выключается**.  
Поэтому первую настройку делали так:

1. Воткнуть TV в **Wi‑Fi** (тот же роутер что и ПК)
2. **Вытащить LAN** на время настройки
3. Включить «Беспроводная отладка» и «Отладка по USB»
4. Пройти pair + connect + tcpip (ниже)
5. Потом можно снова **воткнуть LAN** и работать по `IP:5555`

### Пошагово в cmd (один раз на TV)

ADB лежит в `C:\adb\adb.exe` (ставится через `install.bat`).

**Шаг 1. Сопряжение**

На TV: *Для разработчиков → Беспроводная отладка → Сопряжение с кодом*  
Не закрывай экран. Запиши **IP**, **порт** и **код**.

```text
cd C:\adb
adb kill-server
adb pair 192.168.2.68:40323
```

Подставь свой IP и **порт сопряжения** с TV. Когда спросит код, введи 6 цифр.  
Должно быть: `Successfully paired to ...`  
Если `protocol fault` - выключи/включи беспроводную отладку, открой pair заново (порт уже другой), попробуй снова.

**Шаг 2. Подключение (другой порт!)**

На TV вернись на главный экран «Беспроводная отладка» (не сопряжение).  
Там **другой порт** для connect, например `39119`:

```text
adb connect 192.168.2.68:39119
adb devices
```

В списке должно быть `device`, не `offline`.

**Шаг 3. Переключаем на 5555 (главное!)**

Пока TV подключён по временному порту:

```text
adb -s 192.168.2.68:39119 tcpip 5555
adb connect 192.168.2.68:5555
adb devices
```

После этого в Control Center в поле **Порт ADB** всегда **5555**.

**Шаг 4. В программе**

- IP: тот что у TV в сети (у нас было `192.168.2.72`, потом мог смениться, смотри в настройках TV)
- Порт: **5555**
- «Подключиться» → на TV «Разрешить отладку» → «Всегда»

### Типичные ошибки (мы через них проходили)

| Ошибка | Что значит |
|--------|------------|
| `adb не является командой` | Нет adb.exe, запусти `install.bat` или `C:\adb\adb.exe ...` |
| `protocol fault` на pair | Старый порт/код, TV не на Wi‑Fi, или экран pair закрыли |
| `device not found` на tcpip | Pair не прошёл, сначала `adb connect` по **временному** порту |
| `connect :5555` отказ 10061 | Ещё не делали `tcpip 5555` или TV перезагрузился |
| IP не пингуется | Неверный IP ( DHCP выдал новый ), проверь в настройках сети TV |

### После перезагрузки TV

Иногда нужно снова `adb connect IP:5555`.  
Если 5555 не открывается, повтори pair → connect → `tcpip 5555` по Wi‑Fi.

### Несколько TV в клубе

В «Обзор» добавь каждый TV со **своим IP**. Порт **5555** на всех, если на каждом делали `tcpip 5555`.  
У каждого TV настройка pair делается **отдельно**.

## Как подключить TV (кратко)

1. Первый раз только через Wi‑Fi: pair → connect → `tcpip 5555` (см. выше).
2. На TV: О телевизоре → 7 раз «Номер сборки» → Для разработчиков → отладка.
3. В программе IP TV и порт **5555**, кнопка «Подключиться».
4. Потом можно LAN, если PC и TV в одной подсети `192.168.x.x`.

```text
adb connect 192.168.x.x:5555
```

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
