@echo off
chcp 65001 >nul
cd /d %~dp0
start "" http://127.0.0.1:8900
echo === 订场秒抢网页版 http://127.0.0.1:8900 (关窗口即停) ===
python web.py
