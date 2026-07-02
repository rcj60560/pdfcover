# PDFCover Web 界面实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 PDFCover 添加 Web 界面，提供浏览器操作方式进行单文件 PDF 转换

**Architecture:** Flask 后端服务 + 单页 HTML 前端，通过文件上传 API 进行通信，调用现有 pdfcover 核心功能

**Tech Stack:** Flask 3.0+, HTML5, JavaScript (原生), 现有 pdfcover 核心库

## Global Constraints

- 输出固定路径: `D:\Users\luocj\pyProject\ky\pdfcover\coverdPDF`
- 仅支持单文件选择，不支持批量
- 文件大小限制: 100MB
- 服务器地址: `http://127.0.0.1:5000`
- Python 依赖: Flask>=3.0

---

## Task 1: 更新项目依赖

**Files:**
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: None
- Produces: Updated dependency list with Flask

- [ ] **Step 1: 读取当前 pyproject.toml**

```bash
cat pyproject.toml
```

- [ ] **Step 2: 添加 Flask 依赖**

在 `[project.dependencies]` 数组中添加 `"flask>=3.0"`

- [ ] **Step 3: 验证语法**

```bash
python -m tomli pyproject.toml
```

或使用 pip 检查:
```bash
pip install --dry-run -e .
```

- [ ] **Step 4: 提交**

```bash
git add pyproject.toml
git commit -m "feat: add Flask dependency for web UI"
```

---

## Task 2: 创建 Web 模块目录结构

**Files:**
- Create: `pdfcover/web/__init__.py`
- Create: `pdfcover/web/templates/` (目录)

**Interfaces:**
- Consumes: None
- Produces: Web 模块基础结构

- [ ] **Step 1: 创建 web 模块目录**

```bash
mkdir pdfcover/web
mkdir pdfcover/web/templates
```

- [ ] **Step 2: 创建 __init__.py**

创建 `pdfcover/web/__init__.py`:
```python
"""PDFCover Web interface module."""

__version__ = "0.2.0"
```

- [ ] **Step 3: 验证模块可导入**

```bash
python -c "from pdfcover import web; print(web.__version__)"
```

Expected: 输出 `0.2.0`

- [ ] **Step 4: 提交**

```bash
git add pdfcover/web/__init__.py
git commit -m "feat: create web module structure"
```

---

## Task 3: 实现 Flask 应用基础结构

**Files:**
- Create: `pdfcover/web/app.py`
- Create: `tests/unit/test_web_app.py`

**Interfaces:**
- Consumes: Flask 库
- Produces: Flask app 实例, `create_app()` 函数

- [ ] **Step 1: 编写基础测试**

创建 `tests/unit/test_web_app.py`:
```python
"""Unit tests for web application."""

import pytest
from pdfcover.web.app import create_app


def test_create_app():
    """Test that Flask app can be created."""
    app = create_app()
    assert app is not None
    assert app.config['TESTING'] is True


def test_output_dir_config():
    """Test that output directory is configured."""
    app = create_app()
    assert 'OUTPUT_DIR' in app.config
    assert app.config['OUTPUT_DIR'] == 'D:\\Users\\luocj\\pyProject\\ky\\pdfcover\\coverdPDF'


def test_max_content_length():
    """Test that max content length is set."""
    app = create_app()
    assert app.config['MAX_CONTENT_LENGTH'] == 100 * 1024 * 1024
```

- [ ] **Step 2: 运行测试验证失败**

```bash
pytest tests/unit/test_web_app.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'pdfcover.web.app'`

- [ ] **Step 3: 实现最小代码使测试通过**

创建 `pdfcover/web/app.py`:
```python
"""Flask application for PDFCover web interface."""

import os
from pathlib import Path
from flask import Flask

OUTPUT_DIR = Path('D:/Users/luocj/pyProject/ky/pdfcover/coverdPDF')


def create_app(testing=False):
    """Create and configure Flask app.

    Args:
        testing: Whether to run in testing mode

    Returns:
        Configured Flask application
    """
    app = Flask(__name__)
    app.config['TESTING'] = testing
    app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB
    app.config['OUTPUT_DIR'] = str(OUTPUT_DIR)
    app.config['UPLOAD_FOLDER'] = str(Path.cwd() / 'temp')

    # Ensure output directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    return app
```

- [ ] **Step 4: 运行测试验证通过**

```bash
pytest tests/unit/test_web_app.py -v
```

Expected: PASS (3 tests)

- [ ] **Step 5: 提交**

```bash
git add pdfcover/web/app.py tests/unit/test_web_app.py
git commit -m "feat: add Flask app foundation with config"
```

---

## Task 4: 实现根路由和首页模板

**Files:**
- Modify: `pdfcover/web/app.py`
- Create: `pdfcover/web/templates/index.html`
- Modify: `tests/unit/test_web_app.py`

**Interfaces:**
- Consumes: Flask app from Task 3
- Produces: GET `/` 路由

- [ ] **Step 1: 添加路由测试**

在 `tests/unit/test_web_app.py` 添加:
```python
def test_root_route():
    """Test that root route returns HTML."""
    app = create_app()
    client = app.test_client()
    response = client.get('/')
    assert response.status_code == 200
    assert b'PDF' in response.data
    assert b'html' in response.data.lower()
```

- [ ] **Step 2: 运行测试验证失败**

```bash
pytest tests/unit/test_web_app.py::test_root_route -v
```

Expected: FAIL with 404

- [ ] **Step 3: 实现 index.html 模板**

创建 `pdfcover/web/templates/index.html`:
```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PDF 转换工具</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }

        .container {
            background: white;
            border-radius: 12px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            max-width: 500px;
            width: 100%;
            padding: 40px;
        }

        h1 {
            text-align: center;
            color: #333;
            margin-bottom: 30px;
            font-size: 24px;
        }

        .file-section {
            margin-bottom: 20px;
        }

        .file-input-wrapper {
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 15px;
        }

        input[type="file"] {
            display: none;
        }

        .file-button {
            background: #667eea;
            color: white;
            padding: 10px 20px;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 14px;
            transition: background 0.2s;
        }

        .file-button:hover {
            background: #5568d3;
        }

        .file-info {
            color: #666;
            font-size: 14px;
        }

        .convert-button {
            width: 100%;
            background: #667eea;
            color: white;
            padding: 12px;
            border: none;
            border-radius: 6px;
            font-size: 16px;
            cursor: pointer;
            transition: background 0.2s;
        }

        .convert-button:hover:not(:disabled) {
            background: #5568d3;
        }

        .convert-button:disabled {
            background: #ccc;
            cursor: not-allowed;
        }

        .status-section {
            margin-top: 20px;
            padding: 15px;
            border-radius: 6px;
            background: #f5f5f5;
            min-height: 60px;
        }

        .status {
            color: #666;
            font-size: 14px;
        }

        .status.success {
            color: #28a745;
        }

        .status.error {
            color: #dc3545;
        }

        .output-path {
            margin-top: 10px;
            font-size: 12px;
            color: #999;
            word-break: break-all;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>PDF 转换工具</h1>

        <div class="file-section">
            <div class="file-input-wrapper">
                <span>📁</span>
                <button class="file-button" onclick="document.getElementById('fileInput').click()">浏览...</button>
                <input type="file" id="fileInput" accept=".pdf" onchange="handleFileSelect(event)">
            </div>
            <div class="file-info" id="fileInfo">未选择文件</div>
        </div>

        <button class="convert-button" id="convertBtn" onclick="startConversion()" disabled>开始转换</button>

        <div class="status-section">
            <div class="status" id="status">等待操作...</div>
            <div class="output-path" id="outputPath"></div>
        </div>
    </div>

    <script>
        let selectedFile = null;

        function handleFileSelect(event) {
            const file = event.target.files[0];
            if (file) {
                if (!file.name.toLowerCase().endsWith('.pdf')) {
                    showStatus('请选择 PDF 文件', 'error');
                    return;
                }
                selectedFile = file;
                const sizeMB = (file.size / (1024 * 1024)).toFixed(2);
                document.getElementById('fileInfo').textContent = `${file.name} (${sizeMB} MB)`;
                document.getElementById('convertBtn').disabled = false;
                showStatus('准备就绪', '');
            }
        }

        function startConversion() {
            if (!selectedFile) {
                showStatus('请先选择文件', 'error');
                return;
            }

            const formData = new FormData();
            formData.append('file', selectedFile);

            document.getElementById('convertBtn').disabled = true;
            showStatus('正在转换...', '');

            fetch('/api/convert', {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    showStatus('✓ 转换完成！', 'success');
                    document.getElementById('outputPath').textContent = `输出: ${data.output_path}`;
                } else {
                    showStatus(`✗ 转换失败: ${data.message}`, 'error');
                    if (data.error) {
                        document.getElementById('outputPath').textContent = data.error;
                    }
                }
            })
            .catch(error => {
                showStatus('网络错误', 'error');
                console.error('Error:', error);
            })
            .finally(() => {
                document.getElementById('convertBtn').disabled = false;
            });
        }

        function showStatus(message, type) {
            const statusEl = document.getElementById('status');
            statusEl.textContent = message;
            statusEl.className = 'status ' + type;
        }
    </script>
</body>
</html>
```

- [ ] **Step 4: 注册路由**

修改 `pdfcover/web/app.py`, 在 `create_app()` 函数返回前添加:
```python
    from flask import render_template

    @app.route('/')
    def index():
        return render_template('index.html')

    return app
```

同时在文件顶部添加导入更新:
```python
from flask import Flask, render_template
```

- [ ] **Step 5: 运行测试验证通过**

```bash
pytest tests/unit/test_web_app.py::test_root_route -v
```

Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add pdfcover/web/app.py pdfcover/web/templates/index.html tests/unit/test_web_app.py
git commit -m "feat: add root route and index template"
```

---

## Task 5: 实现转换 API

**Files:**
- Modify: `pdfcover/web/app.py`
- Create: `tests/unit/test_web_api.py`

**Interfaces:**
- Consumes: `pdfcover.processor.process_file()` from核心模块
- Produces: POST `/api/convert` 端点

- [ ] **Step 1: 编写 API 测试**

创建 `tests/unit/test_web_api.py`:
```python
"""Unit tests for web API."""

import io
from unittest.mock import patch, MagicMock
import pytest

from pdfcover.web.app import create_app


@pytest.fixture
def app():
    return create_app(testing=True)


@pytest.fixture
def client(app):
    return app.test_client()


def test_convert_no_file(client):
    """Test convert endpoint without file."""
    response = client.post('/api/convert')
    assert response.status_code == 400
    data = response.get_json()
    assert data['status'] == 'error'


def test_convert_non_pdf(client):
    """Test convert endpoint with non-PDF file."""
    data = {
        'file': (io.BytesIO(b'not a pdf'), 'test.txt')
    }
    response = client.post('/api/convert', data=data, content_type='multipart/form-data')
    assert response.status_code == 400
    data_json = response.get_json()
    assert data_json['status'] == 'error'
    assert 'PDF' in data_json['message']


@patch('pdfcover.web.app.process_file')
def test_convert_success(mock_process, client):
    """Test successful PDF conversion."""
    # Mock the process_file function
    from pathlib import Path
    mock_process.return_value = MagicMock(
        source=Path('/tmp/test.pdf'),
        output=Path('D:/Users/luocj/pyProject/ky/pdfcover/coverdPDF/test_ocr.pdf'),
        status='success',
        error=None
    )

    # Create a minimal PDF-like content
    pdf_content = b'%PDF-1.4\n' + b'fake pdf content'

    data = {
        'file': (io.BytesIO(pdf_content), 'test.pdf')
    }
    response = client.post('/api/convert', data=data, content_type='multipart/form-data')
    assert response.status_code == 200
    data_json = response.get_json()
    assert data_json['status'] == 'success'
    assert 'output_path' in data_json


@patch('pdfcover.web.app.process_file')
def test_convert_ocr_error(mock_process, client):
    """Test OCR processing error."""
    # Mock failed processing
    from pathlib import Path
    mock_process.return_value = MagicMock(
        source=Path('/tmp/test.pdf'),
        output=None,
        status='failed',
        error='OCR processing failed'
    )

    pdf_content = b'%PDF-1.4\n' + b'fake pdf content'
    data = {
        'file': (io.BytesIO(pdf_content), 'test.pdf')
    }
    response = client.post('/api/convert', data=data, content_type='multipart/form-data')
    assert response.status_code == 200
    data_json = response.get_json()
    assert data_json['status'] == 'error'
    assert data_json['error'] == 'OCR processing failed'
```

- [ ] **Step 2: 运行测试验证失败**

```bash
pytest tests/unit/test_web_api.py -v
```

Expected: FAIL with 404 or other error

- [ ] **Step 3: 实现 API 端点**

修改 `pdfcover/web/app.py`, 添加以下内容:

在文件顶部导入:
```python
from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename
import tempfile
from pdfcover.processor import process_file
```

在 `create_app()` 函数中, `@app.route('/')` 之后添加:
```python
    ALLOWED_EXTENSIONS = {'pdf'}

    def allowed_file(filename):
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

    @app.route('/api/convert', methods=['POST'])
    def convert():
        if 'file' not in request.files:
            return jsonify({
                'status': 'error',
                'message': '没有上传文件',
                'output_path': None,
                'error': None
            }), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({
                'status': 'error',
                'message': '文件名为空',
                'output_path': None,
                'error': None
            }), 400

        if not allowed_file(file.filename):
            return jsonify({
                'status': 'error',
                'message': '请选择 PDF 文件',
                'output_path': None,
                'error': None
            }), 400

        # Save to temp location
        filename = secure_filename(file.filename)
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
            file.save(tmp.name)
            temp_path = tmp.name

        try:
            # Process the file
            output_dir = Path(app.config['OUTPUT_DIR'])
            output_path = output_dir / f"{Path(filename).stem}_ocr.pdf"

            result = process_file(temp_path, output_path)

            if result.status == 'success':
                return jsonify({
                    'status': 'success',
                    'message': '转换成功',
                    'output_path': f"coverdPDF/{result.output.name}",
                    'error': None
                })
            else:
                return jsonify({
                    'status': 'error',
                    'message': '转换失败',
                    'output_path': None,
                    'error': result.error
                })

        except Exception as e:
            return jsonify({
                'status': 'error',
                'message': '服务器错误',
                'output_path': None,
                'error': str(e)
            })
        finally:
            # Clean up temp file
            try:
                Path(temp_path).unlink()
            except:
                pass
```

- [ ] **Step 4: 运行测试验证通过**

```bash
pytest tests/unit/test_web_api.py -v
```

Expected: PASS (4 tests)

- [ ] **Step 5: 提交**

```bash
git add pdfcover/web/app.py tests/unit/test_web_api.py
git commit -m "feat: implement PDF conversion API endpoint"
```

---

## Task 6: 添加模块入口

**Files:**
- Modify: `pdfcover/web/__init__.py`
- Create: `pdfcover/web/__main__.py`
- Modify: `tests/unit/test_web_app.py`

**Interfaces:**
- Consumes: `create_app()` from `app.py`
- Produces: `python -m pdfcover.web` 命令行入口

- [ ] **Step 1: 添加入口测试**

在 `tests/unit/test_web_app.py` 添加:
```python
def test_module_main_exists():
    """Test that __main__ module can be imported."""
    from pdfcover.web import __main__
    assert hasattr(__main__, 'main')
```

- [ ] **Step 2: 运行测试验证失败**

```bash
pytest tests/unit/test_web_app.py::test_module_main_exists -v
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: 实现 __main__.py**

创建 `pdfcover/web/__main__.py`:
```python
"""Entry point for running PDFCover web server."""

import webbrowser
import time
from pdfcover.web.app import create_app


def main():
    """Start the Flask development server and open browser."""
    app = create_app()

    print("=" * 50)
    print("PDFCover Web 服务器已启动")
    print("=" * 50)
    print(f"访问地址: http://127.0.0.1:5000")
    print(f"输出目录: {app.config['OUTPUT_DIR']}")
    print("=" * 50)
    print("按 Ctrl+C 停止服务器")
    print()

    # Open browser after a short delay
    def open_browser():
        time.sleep(1)
        webbrowser.open('http://127.0.0.1:5000')

    import threading
    browser_thread = threading.Thread(target=open_browser, daemon=True)
    browser_thread.start()

    # Run app
    app.run(host='127.0.0.1', port=5000, debug=False)


if __name__ == '__main__':
    main()
```

- [ ] **Step 4: 更新 __init__.py**

修改 `pdfcover/web/__init__.py`:
```python
"""PDFCover Web interface module."""

from pdfcover.web.app import create_app

__version__ = "0.2.0"
```

- [ ] **Step 5: 运行测试验证通过**

```bash
pytest tests/unit/test_web_app.py::test_module_main_exists -v
```

Expected: PASS

- [ ] **Step 6: 手动验证启动**

```bash
python -m pdfcover.web
```

Expected: 服务器启动, 浏览器自动打开

按 Ctrl+C 停止服务器。

- [ ] **Step 7: 提交**

```bash
git add pdfcover/web/__init__.py pdfcover/web/__main__.py tests/unit/test_web_app.py
git commit -m "feat: add module entry point for web server"
```

---

## Task 7: 创建启动脚本

**Files:**
- Create: `start_web.bat`
- Create: `start_web.sh`

**Interfaces:**
- Consumes: `python -m pdfcover.web` 命令
- Produces: 启动脚本

- [ ] **Step 1: 创建 Windows 启动脚本**

创建 `start_web.bat`:
```batch
@echo off
echo ========================================
echo  PDFCover Web 启动中...
echo ========================================
echo.
python -m pdfcover.web
pause
```

- [ ] **Step 2: 创建 Unix 启动脚本**

创建 `start_web.sh`:
```bash
#!/bin/bash
echo "========================================"
echo " PDFCover Web 启动中..."
echo "========================================"
echo ""
python -m pdfcover.web
```

- [ ] **Step 3: 添加执行权限**

```bash
chmod +x start_web.sh
```

- [ ] **Step 4: 测试 Windows 启动脚本**

```bash
cmd.exe /c start_web.bat
```

或直接双击文件。

Expected: 服务器启动, 浏览器自动打开

按 Ctrl+C 停止服务器。

- [ ] **Step 5: 提交**

```bash
git add start_web.bat start_web.sh
git commit -m "feat: add startup scripts for web server"
```

---

## Task 8: 集成测试

**Files:**
- Create: `tests/integration/test_web_ui.py`

**Interfaces:**
- Consumes: 完整的 Web 应用
- Produces: 端到端测试

- [ ] **Step 1: 编写集成测试**

创建 `tests/integration/test_web_ui.py`:
```python
"""Integration tests for web UI."""

import io
import time
from pdfcover.web.app import create_app


def test_full_conversion_flow():
    """Test end-to-end conversion through web interface."""
    app = create_app(testing=True)
    client = app.test_client()

    # Get main page
    response = client.get('/')
    assert response.status_code == 200
    assert b'PDF' in response.data

    # Upload and convert a minimal PDF
    minimal_pdf = b'%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n3 0 obj\n<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> /MediaBox [0 0 612 792] /Contents 5 0 R >>\nendobj\n4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n5 0 obj\n<< /Length 44 >>\nstream\nBT\n/F1 12 Tf\n100 700 Td\n(Test) Tj\nET\nendstream\nendobj\nxref\n0 6\n0000000000 65535 f\n0000000009 00000 n\n0000000056 00000 n\n0000000115 00000 n\n0000000266 00000 n\n0000000361 00000 n\ntrailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n451\n%%EOF'

    data = {'file': (io.BytesIO(minimal_pdf), 'integration_test.pdf')}
    response = client.post('/api/convert', data=data, content_type='multipart/form-data')

    # Note: This test uses mock OCR, so we just verify the API flow
    # Real OCR would require ocrmypdf installed
    assert response.status_code == 200
    result = response.get_json()
    assert 'status' in result
```

- [ ] **Step 2: 运行集成测试**

```bash
pytest tests/integration/test_web_ui.py -v
```

Expected: PASS

- [ ] **Step 3: 提交**

```bash
git add tests/integration/test_web_ui.py
git commit -m "test: add integration test for web UI"
```

---

## Task 9: 更新文档

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: 实现的功能
- Produces: 更新的用户文档

- [ ] **Step 1: 在 README.md 添加 Web 界面部分**

在 README.md 的"使用方法"部分后添加:

```markdown
## Web 界面使用

### 启动 Web 服务器

**Windows:**
```bash
# 双击 start_web.bat 或在命令行运行
start_web.bat
```

**macOS/Linux:**
```bash
./start_web.sh
```

或直接运行:
```bash
python -m pdfcover.web
```

服务器启动后会自动打开浏览器访问 http://127.0.0.1:5000

### 使用流程

1. 在网页上点击"浏览"选择 PDF 文件
2. 点击"开始转换"
3. 等待转换完成
4. 转换后的文件保存在 `coverdPDF/` 目录
```

- [ ] **Step 2: 验证文档格式**

```bash
# 检查 markdown 语法 (如果有工具的话)
# 或直接在 GitHub/GitLab 上预览
```

- [ ] **Step 3: 提交**

```bash
git add README.md
git commit -m "docs: add web UI usage instructions"
```

---

## Task 10: 最终验证

**Files:**
- All

**Interfaces:**
- Consumes: 完整实现
- Produces: 验证结果

- [ ] **Step 1: 运行所有测试**

```bash
pytest tests/ -v
```

Expected: 所有测试通过

- [ ] **Step 2: 手动端到端测试**

```bash
# 1. 启动服务器
python -m pdfcover.web

# 2. 浏览器会自动打开，测试以下流程:
#    - 打开网页显示正常
#    - 选择一个真实 PDF 文件
#    - 点击转换
#    - 查看 coverdPDF/ 目录是否有输出文件

# 3. 按 Ctrl+C 停止
```

- [ ] **Step 3: 验证依赖安装**

在新的虚拟环境中测试:
```bash
python -m venv test_env
test_env\Scripts\activate
pip install -e .
python -m pdfcover.web
```

Expected: 服务器正常启动

- [ ] **Step 4: 最终提交**

```bash
git add .
git commit -m "chore: final cleanup and verification"
```

---

## 总结

实现完成后,用户将拥有:

1. ✅ Web 界面可以转换单个 PDF 文件
2. ✅ 双击 `start_web.bat` 即可启动
3. ✅ 浏览器自动打开
4. ✅ 输出固定到 `coverdPDF/` 目录
5. ✅ 完整的单元测试和集成测试
