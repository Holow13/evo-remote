# Control Center

Короче, это наша панель для клуба: пульт на TV, таймер сессии, можно несколько телеков сразу, и таймер в углу экрана (видно даже когда PS или HDMI).

Мы гоняли на **Haier MatrixTV FR** (Google TV). Главное: **ПК и TV в одной сети** (один роутер).

---

## Быстрый старт (если лень читать дальше)

1. **`install.bat`** — один раз, поставит ADB и всё для Python  
2. **`start.bat`** — запуск программы  
3. На TV включи отладку, вбей IP в программе, жми «Подключиться»

Нужен таймер в углу TV?

1. **`build_overlay.bat`** (нужна Java 17)  
2. **`install_overlay.bat`** (кидает APK на TV)

---

## Что ставит install.bat

Сам качает **ADB** и Python-библиотеки. Руками ничего не надо, если есть интернет.

ADB окажется тут: `C:\adb\` или `%LOCALAPPDATA%\evo-remote\platform-tools\`

Инет интернета на клубном ПК? Скачай zip на домашнем:  
https://dl.google.com/android/repository/platform-tools-latest-windows.zip  
Кинь в папку `downloads\`, снова **`install.bat`**.

**Python** если нет вообще: https://www.python.org/downloads/ (3.10+)  
Или `winget install Python.Python.3.12`  
Не забудь галочку **Add python.exe to PATH**.

---

## Ссылки на софт (если build_overlay не качает)

Скрипт сам пробует. Не вышло — кидай файлы в **`downloads\`**, смотри `downloads/README.txt`.

| Что | Откуда | Зеркало |
|-----|--------|---------|
| Java 17 | https://adoptium.net/temurin/releases/?version=17 | |
| Android SDK tools | https://dl.google.com/android/repository/commandlinetools-win-11076708_latest.zip | https://mirrors.cloud.tencent.com/AndroidSDK/commandlinetools-win-11076708_latest.zip |
| Gradle 8.5 | https://services.gradle.org/distributions/gradle-8.5-bin.zip | https://github.com/gradle/gradle-distributions/releases/download/v8.5.0/gradle-8.5-bin.zip |
| gradle-wrapper.jar | https://github.com/gradle/gradle/raw/v8.5.0/gradle/wrapper/gradle-wrapper.jar | raw.githubusercontent.com вариант в OVERLAY_DOWNLOADS.txt |

Полный список: **`OVERLAY_DOWNLOADS.txt`**

**По желанию:** [Scrcpy](https://github.com/Genymobile/scrcpy/releases) (удобнее смотреть экран TV), [Android Studio](https://developer.android.com/studio) (если лень отдельно Java/SDK).

---

## Bat-файлы (что куда жать)

| Файл | Зачем |
|------|-------|
| `install.bat` | Первый запуск, ставит всё |
| `setup.bat` | То же |
| `start.bat` | Сама программа |
| `build_overlay.bat` | Собрать APK таймера |
| `install_overlay.bat` | Залить APK на TV |

---

## Что внутри программы

- **Обзор** — список TV, жмёшь на TV-1 и попадаешь в таймер/пульт  
- **Клуб · Таймер** — отсчёт, время вводишь сам (60, 90:00, 1:30:00)  
- **Пульт TV** — как пульт: стрелки, громкость, вкл/выкл, YouTube и т.д.  
- **Система TV** — экран на ПК, терминал, файлы, приложения  
- **Компьютер** — вырубить/уснуть/заблокировать этот ПК  
- **Устройства** — разбудить другой ПК по сети (WoL)

У каждого TV свой IP и свой таймер. В программе порт почти всегда **5555**.

---

## ADB и порты — как мы настраивали Haier (важно!)

Тут мы долго мучились, так что запиши. На Google TV **три разных порта**, не один.

### Не путай порты

| Какой | Зачем | Пример |
|-------|-------|--------|
| Порт **pair** (сопряжение) | Только `adb pair` + код с TV | `:40323` |
| Порт **connect** (временный) | Первый `adb connect` после pair | `:39119` |
| **5555** | Наш рабочий порт для клуба | `:5555` |

Цифры 40323 / 39119 **каждый раз новые** — TV показывает на экране «Беспроводная отладка».  
**5555** включаем сами (`tcpip 5555`) и в Control Center всегда его пишем.

### Почему сначала Wi‑Fi, а не LAN

На Haier если воткнут **кабель в роутер**, «Беспроводная отладка» **сразу отваливается**. Мы так и словили.

Первый раз делай так:

1. TV на **Wi‑Fi** (тот же роутер что ПК)  
2. **Вынь LAN** пока настраиваешь  
3. Включи «Беспроводная отладка» + «Отладка по USB»  
4. Пройди pair → connect → tcpip (ниже)  
5. Потом **можно обратно LAN** и жить на `IP:5555`

### Разработчик на TV (один раз)

Настройки → Система → О телевизоре → **7 раз** по «Номер сборки»  
Потом: Для разработчиков → Отладка по USB ✓ → Беспроводная отладка ✓

(На французском Haier: Paramètres → Système → Options pour les développeurs)

### Команды в cmd (копируй, подставляй свой IP)

ADB после `install.bat`: `C:\adb\adb.exe`

**1) Pair — сопряжение**

На TV: *Беспроводная отладка → Сопряжение с кодом*. **Не закрывай экран.**  
Запиши IP, порт и 6 цифр.

```text
cd C:\adb
adb kill-server
adb pair 192.168.2.68:40323
```

Свой IP и **порт с pair-экрана**. Код вводишь когда спросит.  
Норма: `Successfully paired to ...`  
Косяк `protocol fault`? Выруби/вруби отладку, открой pair снова (порт уже другой!), TV точно на Wi‑Fi.

**2) Connect — но порт уже другой!**

На TV главный экран «Беспроводная отладка» (не pair). Там **новый порт**, типа 39119:

```text
adb connect 192.168.2.68:39119
adb devices
```

Нужно `device`, не `offline`.

**3) Переключаем на 5555 — это то, что нам нужно**

```text
adb -s 192.168.2.68:39119 tcpip 5555
adb connect 192.168.2.68:5555
adb devices
```

**4) В Control Center**

- IP — смотри в настройках TV ( DHCP может поменять, у нас было 192.168.2.72 )  
- Порт: **5555**  
- Подключиться → на TV «Разрешить» + «Всегда»

### Когда всё идёт не так (мы уже видели)

| Что пишет | Что делать |
|-----------|------------|
| `adb` не команда | `install.bat` или пиши `C:\adb\adb.exe` |
| `protocol fault` | Старый код/порт, закрыл экран pair, или TV не на Wi‑Fi |
| `device not found` на tcpip | Pair не прошёл, connect по **временному** порту сначала |
| `connect :5555` отказ | Не делали `tcpip 5555` или TV перезагрузился |
| ping не идёт | IP сменился, глянь в настройках сети TV |

### TV перезагрузили

Часто хватит `adb connect IP:5555`.  
Не коннектится — повтори pair → connect → tcpip по Wi‑Fi.

### Несколько TV в клубе

В «Обзор» жми **+ Добавить TV**, у каждого свой IP.  
На **каждом** TV отдельно делаешь pair и `tcpip 5555`.  
Потом кликаешь TV-1 / TV-2 и работаешь с нужным.

### Таймер в углу

Один раз: `build_overlay.bat` → `install_overlay.bat`  
На TV разреши Evo Timer «Поверх других приложений».

---

## Скачать с GitHub

https://github.com/Holow13/evo-remote

```text
git clone git@github.com:Holow13/evo-remote.git
cd evo-remote
install.bat
start.bat
```

Если что — пиши, разбирались на Haier, на других Google TV должно быть похоже.
