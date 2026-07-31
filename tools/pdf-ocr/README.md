# PDFCover

将影印版 PDF 文件转换为可搜索、可选中内容的标准 PDF 文件。

## 特性

- ✅ 简洁的单函数 API
- ✅ 高准确率 OCR 配置（英文优化）
- ✅ 自动跳过已转换文件
- ✅ 单个文件失败不影响整体处理
- ✅ 详细的处理结果报告

## 安装

### 1. 安装系统依赖

**Windows:**
```bash
# 使用 Chocolatey（推荐）
choco install tesseract -y

# 或手动下载安装包
# https://github.com/UB-Mannheim/tesseract/wiki
```

**macOS:**
```bash
brew install tesseract ocrmypdf
```

**Linux:**
```bash
apt-get install tesseract-ocr ocrmypdf
```

### 2. 安装 Python 包

```bash
pip install pdfcover
```

或从源码安装：

```bash
git clone https://github.com/yourusername/pdfcover.git
cd pdfcover
pip install -e .
```

## 使用方法

### 基本用法

```python
from pdfcover import convert_folder

# 转换文件夹中的所有 PDF
results = convert_folder("/path/to/pdfs")

# 查看结果
for r in results:
    if r['status'] == 'success':
        print(f"✓ {r['source']} → {r['output']}")
    elif r['status'] == 'failed':
        print(f"✗ {r['source']}: {r['error']}")
    else:
        print(f"○ {r['source']}: 已跳过")
```

### 高级用法

```python
from pdfcover import convert_folder

# 自定义输出后缀
results = convert_folder("/path/to/pdfs", output_suffix="_searchable")

# 处理子文件夹（暂未实现）
# results = convert_folder("/path/to/pdfs", recursive=True)
```

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

## API 文档

### `convert_folder(folder_path, output_suffix="_ocr", recursive=False)`

扫描文件夹并转换所有影印 PDF 为可搜索 PDF。

**参数:**
- `folder_path` (str): PDF 所在文件夹路径
- `output_suffix` (str): 输出文件后缀，默认 "_ocr"
- `recursive` (bool): 是否递归处理子文件夹（默认: False，暂未实现）

**返回:**
- `list[dict]`: 转换结果列表，每个元素包含:
  - `source` (str): 原文件路径
  - `output` (str): 输出文件路径
  - `status` (str): "success" | "failed" | "skipped"
  - `error` (str | None): 错误信息（如有）

**异常:**
- `FileNotFoundError`: 文件夹不存在

## 示例

### 转换单个文件夹

```python
from pdfcover import convert_folder

results = convert_folder("./documents", output_suffix="_ocr")

# 统计
success = sum(1 for r in results if r['status'] == 'success')
failed = sum(1 for r in results if r['status'] == 'failed')

print(f"成功: {success}, 失败: {failed}")
```

### 批量处理

```python
from pdfcover import convert_folder
import os

# 处理多个文件夹
for folder in ['batch1', 'batch2', 'batch3']:
    print(f"处理 {folder}...")
    results = convert_folder(f"./scans/{folder}")
    # 保存结果...
```

## 依赖

- Python 3.10+
- ocrmypdf >= 14.0
- pypdf >= 3.0
- Tesseract OCR（系统级依赖）

## 开发

```bash
# 克隆仓库
git clone https://github.com/yourusername/pdfcover.git
cd pdfcover

# 创建虚拟环境
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # macOS/Linux

# 安装开发依赖
pip install -e ".[dev]"

# 运行测试
pytest tests/unit/ -v
```

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！

## 更新日志

### 0.1.0 (2026-07-01)
- 初始版本发布
- 支持批量 PDF 转换
- 高准确率英文 OCR 配置
- 自动跳过已转换文件
