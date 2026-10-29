@echo off
chcp 65001 >nul
cd /d %~dp0
echo === 订场秒抢(8:50换好token后双击我) ===
python snipe.py snipe
pause
