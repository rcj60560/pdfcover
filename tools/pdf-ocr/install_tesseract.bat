@echo off
REM PDFCover - Tesseract OCR 安装脚本
REM 需要以管理员身份运行

echo ============================================
echo PDFCover - Tesseract OCR 安装
echo ============================================
echo.
echo 此脚本将自动安装 Tesseract OCR
echo 需要管理员权限...
echo.

REM 检查管理员权限
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [错误] 需要管理员权限
    echo 请右键点击此文件，选择"以管理员身份运行"
    pause
    exit /b 1
)

echo [1/2] 使用 Chocolatey 安装 Tesseract OCR...
choco install tesseract -y

if %errorLevel% equ 0 (
    echo.
    echo [成功] Tesseract OCR 已安装
    echo.
    echo [2/2] 验证安装...
    tesseract --version
    echo.
    echo ============================================
    echo 安装完成！现在可以运行测试：
    echo   python test_convert.py
    echo ============================================
) else (
    echo.
    echo [失败] Chocolatey 安装失败
    echo 请尝试手动安装：
    echo 1. 访问 https://github.com/UB-Mannheim/tesseract/wiki
    echo 2. 下载 tesseract-ocr-w64-setup-5.5.x.exe
    echo 3. 运行安装程序
    echo 4. 将安装路径添加到系统 PATH
)

pause
