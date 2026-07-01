# PDFCover 设计文档

**日期:** 2026-07-01
**状态:** 已批准
**作者:** Claude

## 1. 概述

PDFCover 是一个简洁的 Python 库，用于将影印版 PDF 文件转换为可搜索、可选中内容的标准 PDF。

### 1.1 核心目标

- 将影印版 PDF 转换为包含可搜索文本层的标准 PDF
- 专注于英文 PDF 处理
- 提供最高准确率的 OCR 识别
- 简洁的单函数 API

### 1.2 约束条件

- 仅关心文本内容，图片可忽略
- 使用 OCRmyPDF 作为核心 OCR 引擎
- 最高准确率优先于处理速度

---

## 2. 核心接口

### 2.1 主 API

```python
def convert_folder(
    folder_path: str,
    output_suffix: str = "_ocr",
    recursive: bool = False
) -> list[dict]:
    """
    扫描文件夹并转换所有影印PDF为可搜索PDF

    Args:
        folder_path: PDF所在文件夹路径
        output_suffix: 输出文件后缀，默认 "_ocr"
        recursive: 是否递归处理子文件夹

    Returns:
        转换结果列表，每个元素包含:
        {
            "source": "原文件路径",
            "output": "输出文件路径",
            "status": "success/failed/skipped",
            "error": "错误信息(如有)"
        }
    """
```

### 2.2 使用示例

```python
from pdfcover import convert_folder

# 基本用法
results = convert_folder("/path/to/pdfs")

# 查看结果
for r in results:
    if r['status'] == 'success':
        print(f"✓ {r['source']} → {r['output']}")
    else:
        print(f"✗ {r['source']}: {r.get('error', 'Unknown')}")
```

---

## 3. 架构设计

### 3.1 项目结构

```
pdfcover/
├── pdfcover/
│   ├── __init__.py       # 导出 convert_folder
│   ├── converter.py      # 主入口和协调逻辑
│   ├── scanner.py        # 文件扫描
│   ├── processor.py      # OCR处理封装
│   └── exceptions.py     # 异常定义
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
├── docs/
│   └── superpowers/specs/
├── pyproject.toml
├── README.md
└── LICENSE
```

### 3.2 组件职责

| 组件 | 职责 |
|------|------|
| `scanner.py` | 扫描文件夹，过滤PDF文件，检查是否已转换 |
| `processor.py` | 封装OCRmyPDF调用，处理单个文件转换 |
| `converter.py` | 协调扫描器和处理器，聚合结果 |
| `exceptions.py` | 自定义异常类 |

### 3.3 数据流

```
folder_path → Scanner → PDF文件列表
                         ↓
                      Processor → 逐个OCR处理
                         ↓
                      结果聚合 → 返回
```

---

## 4. OCR 配置

使用 OCRmyPDF 的高准确率配置：

```python
OCR_CONFIG = {
    "output_type": "pdf",           # 保留原图片，添加文本层
    "language": "eng",              # 英文识别
    "image_dpi": 300,              # 高DPI保证准确率
    "oversample": 3,               # 过采样提高准确率
    "force_ocr": True,             # 强制OCR（即使已有文本层）
    "optimize": 1,                 # 轻度优化
    "deskew": True,                 # 自动纠偏
    "clean": True,                  # 清理噪点
}
```

等效命令行：
```bash
ocrmypdf --output-type pdf \
         --language eng \
         --image-dpi 300 \
         --oversample 3 \
         --force-ocr \
         --optimize 1 \
         --deskew \
         --clean \
         input.pdf output_ocr.pdf
```

---

## 5. 错误处理

### 5.1 异常定义

```python
class PDFCoverError(Exception):
    """基础异常"""
    pass

class OCRError(PDFCoverError):
    """OCR处理失败"""
    pass

class InvalidPDFError(PDFCoverError):
    """无效的PDF文件"""
    pass
```

### 5.2 处理策略

| 场景 | 处理方式 |
|------|----------|
| 单个文件失败 | 记录错误，继续处理其他文件 |
| 文件夹不存在 | 抛出 `FileNotFoundError` |
| OCRmyPDF未安装 | 抛出清晰的安装提示 |

### 5.3 结果状态

| status | 说明 |
|--------|------|
| `success` | 转换成功 |
| `failed` | 转换失败（error字段包含原因） |
| `skipped` | 已存在输出文件且可读 |

---

## 6. 依赖管理

### 6.1 Python 依赖

```toml
[project]
dependencies = [
    "ocrmypython>=1.9",      # OCRmyPDF的Python包装
    "pypdf>=3.0",            # PDF读取和验证
]
```

### 6.2 系统依赖

用户需要先安装系统级 OCRmyPDF：

- **Windows:** `choco install tesseract` 或下载安装包
- **macOS:** `brew install tesseract ocrmypdf`
- **Linux:** `apt-get install tesseract-ocr ocrmypdf`

### 6.3 安装流程

```bash
# 1. 安装系统依赖（见上方）
# 2. 安装 Python 包
pip install pdfcover
```

---

## 7. 测试策略

### 7.1 测试结构

```
tests/
├── unit/              # 单元测试
│   ├── test_scanner.py
│   ├── test_processor.py
│   └── test_converter.py
├── integration/       # 集成测试
│   └── test_end_to_end.py
└── fixtures/          # 测试文件
    └── sample_scan.pdf
```

### 7.2 测试策略

- 单元测试使用 Mock OCRmyPDF 调用
- 集成测试使用真实 OCR（标记为 slow）
- 测试边界：空文件夹、无PDF、损坏的PDF
- 使用小型测试 PDF（单页）

---

## 8. 关键特性

- ✅ 简洁的单函数 API
- ✅ 高准确率 OCR 配置
- ✅ 自动跳过已转换文件
- ✅ 单个文件失败不影响整体
- ✅ 详细的处理结果报告
- ✅ 英文 PDF 优化

---

## 9. 版本历史

| 版本 | 日期 | 说明 |
|------|------|------|
| 0.1.0 | 2026-07-01 | 初始设计 |
