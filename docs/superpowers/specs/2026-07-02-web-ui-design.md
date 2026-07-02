# PDFCover Web 界面设计文档

**日期:** 2026-07-02
**状态:** 已批准
**作者:** Claude

## 1. 概述

为 PDFCover 添加 Web 界面，提供简单的浏览器操作界面来转换 PDF 文件。

### 1.1 核心目标

- 提供友好的 Web 界面进行单文件 PDF 转换
- 双击启动，自动打开浏览器
- 本地使用，固定输出目录

### 1.2 约束条件

- 输出固定到: `D:\Users\luocj\pyProject\ky\pdfcover\coverdPDF`
- 仅支持单个文件选择（不支持批量）
- 简单的进度提示即可

---

## 2. 整体架构

```
用户运行 start_web.bat
    ↓
启动 Flask 服务器 (http://127.0.0.1:5000)
    ↓
自动打开浏览器
    ↓
用户在网页操作 → Flask 调用 pdfcover 核心功能
```

---

## 3. 网页界面设计

### 3.1 页面布局

```
┌─────────────────────────────────────────┐
│         PDF 转换工具                      │
├─────────────────────────────────────────┤
│                                         │
│  📁 选择文件: [浏览...]                  │
│                                         │
│  已选择: sample.pdf (2.3 MB)            │
│                                         │
│  [开始转换]                              │
│                                         │
├─────────────────────────────────────────┤
│  状态:                                   │
│  ● 正在转换...                           │
│  ✓ 转换完成！                            │
│     输出: coverdPDF/sample_ocr.pdf      │
└─────────────────────────────────────────┘
```

### 3.2 交互流程

1. **初始状态** - 显示"选择文件"按钮
2. **选择文件** - 显示文件名和大小
3. **点击转换** - 按钮变灰，显示"正在转换..."
4. **完成** - 显示"转换完成！" + 输出路径

### 3.3 样式

- 居中卡片布局
- 清晰的按钮和状态提示
- 响应式设计

---

## 4. 后端 API 设计

### 4.1 Flask 应用 (`web/app.py`)

```python
# 接口
POST /api/convert
    请求: multipart/form-data with file
    返回: {
        "status": "success" | "error",
        "message": "转换成功" | 错误信息,
        "output_path": "coverdPDF/xxx_ocr.pdf" | None,
        "error": 错误详情 | None
    }
```

### 4.2 核心逻辑

1. 接收上传的 PDF 文件
2. 保存到临时位置
3. 调用 `pdfcover.processor.process_file()` 进行转换
4. 输出到固定目录
5. 返回结果

---

## 5. 目录结构

```
pdfcover/
├── pdfcover/
│   ├── __init__.py
│   ├── converter.py
│   ├── scanner.py
│   ├── processor.py
│   ├── config.py
│   ├── exceptions.py
│   └── web/              # 新增
│       ├── __init__.py
│       ├── app.py        # Flask 应用
│       └── templates/    # HTML 模板
│           └── index.html
├── start_web.bat         # 新增 - Windows 启动
├── start_web.sh          # 新增 - macOS/Linux 启动
└── tests/
```

---

## 6. 启动方式

### 6.1 Windows (start_web.bat)

```batch
@echo off
echo Starting PDFCover Web...
python -m pdfcover.web
```

### 6.2 macOS/Linux (start_web.sh)

```bash
#!/bin/bash
echo "Starting PDFCover Web..."
python -m pdfcover.web
```

### 6.3 运行效果

1. 双击启动脚本
2. 命令行显示: "服务器已启动: http://127.0.0.1:5000"
3. 浏览器自动打开网页

---

## 7. 输出目录

固定输出路径: `D:\Users\luocj\pyProject\ky\pdfcover\coverdPDF`

如果目录不存在，自动创建。

---

## 8. 配置

### 8.1 Flask 配置

```python
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB
app.config['UPLOAD_FOLDER'] = temp_dir
OUTPUT_DIR = 'D:\\Users\\luocj\\pyProject\\ky\\pdfcover\\coverdPDF'
```

### 8.2 CORS

本地运行，不需要 CORS 配置。

---

## 9. 错误处理

| 场景 | 处理方式 |
|------|----------|
| 非 PDF 文件 | 返回错误，提示"请选择 PDF 文件" |
| 文件过大 | 返回错误，提示大小限制 |
| OCR 失败 | 返回错误信息 |
| 输出目录无法创建 | 返回错误 |

---

## 10. 依赖更新

```toml
[project]
dependencies = [
    "ocrmypdf>=14.0",
    "pypdf>=3.0",
    "flask>=3.0",           # 新增
]
```

---

## 11. 实现清单

- [ ] 创建 `pdfcover/web/` 目录结构
- [ ] 实现 `web/app.py` Flask 应用
- [ ] 实现 `web/templates/index.html` 界面
- [ ] 创建 `start_web.bat` 启动脚本
- [ ] 创建 `start_web.sh` 启动脚本
- [ ] 更新 `pdfcover/__init__.py` 添加 web 模块
- [ ] 更新 `pyproject.toml` 添加 Flask 依赖
- [ ] 测试端到端流程

---

## 12. 版本历史

| 版本 | 日期 | 说明 |
|------|------|------|
| 0.2.0 | 2026-07-02 | Web 界面设计 |
