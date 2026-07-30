@echo off
cd /d "%~dp0"
title IELTS Audio Player - http://127.0.0.1:8000/
"C:\Users\luocj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" dev_server.py 8000
echo.
echo Server stopped. Press any key to close this window.
pause >nul
