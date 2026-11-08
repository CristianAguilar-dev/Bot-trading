@echo off
title Servidor de Trading Movil (Telegram)
cd /d "%~dp0"
chcp 65001 > nul
python telegram_bot.py
pause
