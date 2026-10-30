@echo off
chcp 65001 >nul
cd /d %~dp0
echo === 订场取证观察(等到9点放场,只探测不下单,证据落盘 evidence\) ===
python snipe.py observe
pause
