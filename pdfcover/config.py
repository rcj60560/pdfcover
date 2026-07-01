"""OCR configuration for PDFCover."""

from typing import Final

# OCRmyPDF configuration for high accuracy English OCR
# See: https://ocrmypdf.readthedocs.io/
OCR_CONFIG: Final = {
    "output_type": "pdf",           # Keep images, add text layer
    "language": "eng",              # English OCR
    "image_dpi": 300,              # High DPI for accuracy
    "oversample": 3,                # Oversample for better accuracy
    "force_ocr": True,             # Force OCR even if text exists
    "optimize": 1,                  # Light optimization
    "deskew": True,                 # Auto-rotate skewed pages
    # Note: 'clean' removed - requires unpaper external program
}

# File extension for output files
DEFAULT_OUTPUT_SUFFIX: Final = "_ocr"
