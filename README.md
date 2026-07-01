# PDFCover

Convert scanned PDF files to searchable, selectable PDFs.

## Installation

```bash
# Install system dependencies first
# Windows: choco install tesseract
# macOS: brew install tesseract ocrmypdf
# Linux: apt-get install tesseract-ocr ocrmypdf

pip install pdfcover
```

## Usage

```python
from pdfcover import convert_folder

results = convert_folder("/path/to/pdfs")

for r in results:
    if r['status'] == 'success':
        print(f"✓ {r['source']} → {r['output']}")
```
