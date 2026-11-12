@echo off
chcp 65001 > nul
title Bunu Kim Söyledi? - Oyun Sunucusu
cd /d "%~dp0"

echo ====================================================
echo 🎮 BUNU KİM SÖYLEDİ? - Wi-Fi Sosyal Parti Oyunu
echo ====================================================
echo.
echo [1/2] Gerekli paketler kontrol ediliyor...
python -m pip install -r requirements.txt --quiet

echo [2/2] Oyun sunucusu başlatılıyor...
echo.
python main.py
pause
