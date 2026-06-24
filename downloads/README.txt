Офлайн-установка (если нет интернета на ПК клуба)
================================================

Положите сюда файлы — install.bat подхватит их автоматически.

1) platform-tools (ADB)
   Скачать: https://dl.google.com/android/repository/platform-tools-latest-windows.zip
   Имя файла должно содержать "platform-tools", например:
   platform-tools-latest-windows.zip

2) Сборка overlay (таймер на TV) — опционально, см. OVERLAY_DOWNLOADS.txt:
   - commandlinetools-win-....zip
   - gradle-8.5-bin.zip
   - gradle-wrapper.jar
   - OpenJDK 17 MSI (openjdk / temurin в имени)

После копирования файлов запустите install.bat (или build_overlay.bat для APK).
