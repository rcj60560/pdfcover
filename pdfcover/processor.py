"""OCR processing wrapper for PDF files."""

from dataclasses import dataclass
from pathlib import Path
from pypdf import PdfReader
from pdfcover.config import OCR_CONFIG


@dataclass
class ProcessResult:
    """Result of processing a single PDF file."""
    source: Path
    output: Path
    status: str  # "success", "failed"
    error: str | None = None


def process_file(source: Path, output: Path) -> ProcessResult:
    """
    Process a single PDF file with OCR.

    Args:
        source: Path to source PDF file
        output: Path to output PDF file

    Returns:
        ProcessResult with status and error information
    """
    try:
        # Validate input PDF
        try:
            with open(source, "rb") as f:
                PdfReader(f)
        except Exception as e:
            return ProcessResult(
                source=source,
                output=output,
                status="failed",
                error=f"Invalid PDF: {str(e)}"
            )

        # Import OCRmyPDF (may not be installed)
        try:
            import ocrmypdf
        except ImportError as e:
            return ProcessResult(
                source=source,
                output=output,
                status="failed",
                error=f"OCRmyPDF not installed. Install with: pip install ocrmypdf"
            )

        # Run OCR
        try:
            ocrmypdf.ocr(
                str(source),
                str(output),
                **OCR_CONFIG
            )
            return ProcessResult(
                source=source,
                output=output,
                status="success"
            )
        except Exception as e:
            return ProcessResult(
                source=source,
                output=output,
                status="failed",
                error=f"OCR failed: {str(e)}"
            )

    except Exception as e:
        return ProcessResult(
            source=source,
            output=output,
            status="failed",
            error=f"Unexpected error: {str(e)}"
        )
