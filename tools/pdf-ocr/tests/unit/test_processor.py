import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from pdfcover.processor import ProcessResult, process_file
from pdfcover.exceptions import OCRError, InvalidPDFError


@pytest.fixture
def sample_pdf(tmp_path):
    """Create a sample PDF file."""
    pdf_file = tmp_path / "input.pdf"
    pdf_file.write_bytes(b"%PDF-1.4\n%fake pdf content")
    return pdf_file


def test_process_result_dataclass():
    """ProcessResult should hold result data."""
    result = ProcessResult(
        source=Path("/path/doc.pdf"),
        output=Path("/path/doc_ocr.pdf"),
        status="success"
    )
    assert result.source.name == "doc.pdf"
    assert result.status == "success"
    assert result.error is None


def test_process_result_with_error():
    """ProcessResult can hold error information."""
    result = ProcessResult(
        source=Path("/path/doc.pdf"),
        output=Path("/path/doc_ocr.pdf"),
        status="failed",
        error="OCR failed: timeout"
    )
    assert result.status == "failed"
    assert result.error == "OCR failed: timeout"


@patch("builtins.__import__")
@patch("pdfcover.processor.PdfReader")
def test_process_file_success(mock_reader, mock_import, sample_pdf):
    """process_file should call OCRmyPDF and return success."""
    # Mock PdfReader to pass PDF validation
    mock_reader.return_value = MagicMock()

    # Mock import to return a mock ocrmypdf module
    mock_ocrmypdf = MagicMock()
    mock_ocrmypdf.ocr.return_value = None

    def import_side_effect(name, *args, **kwargs):
        if name == "ocrmypdf":
            return mock_ocrmypdf
        return __import__(name, *args, **kwargs)

    mock_import.side_effect = import_side_effect

    output_path = sample_pdf.parent / "input_ocr.pdf"
    result = process_file(sample_pdf, output_path)

    assert result.status == "success"
    assert result.source == sample_pdf
    assert result.output == output_path


@patch("builtins.__import__")
@patch("pdfcover.processor.PdfReader")
def test_process_file_ocr_failure(mock_reader, mock_import, sample_pdf):
    """process_file should handle OCRmyPDF errors."""
    # Mock PdfReader to pass PDF validation
    mock_reader.return_value = MagicMock()

    mock_ocrmypdf = MagicMock()
    mock_ocrmypdf.ocr.side_effect = Exception("OCR failed")

    def import_side_effect(name, *args, **kwargs):
        if name == "ocrmypdf":
            return mock_ocrmypdf
        return __import__(name, *args, **kwargs)

    mock_import.side_effect = import_side_effect

    output_path = sample_pdf.parent / "input_ocr.pdf"
    result = process_file(sample_pdf, output_path)

    assert result.status == "failed"
    assert "OCR failed" in result.error


@patch("builtins.__import__")
def test_process_file_invalid_pdf(mock_import, sample_pdf):
    """process_file should detect invalid PDFs."""
    # Mock pypdf to raise error on PDF read
    with patch("pdfcover.processor.PdfReader") as mock_reader:
        mock_reader.side_effect = Exception("Invalid PDF")

        output_path = sample_pdf.parent / "input_ocr.pdf"
        result = process_file(sample_pdf, output_path)

        assert result.status == "failed"
        assert "Invalid PDF" in result.error or "not a valid PDF" in result.error.lower()


@patch("builtins.__import__")
@patch("pdfcover.processor.PdfReader")
def test_process_file_ocrmypdf_not_installed(mock_reader, mock_import, sample_pdf):
    """process_file should handle OCRmyPDF not installed."""
    # Mock PdfReader to pass PDF validation
    mock_reader.return_value = MagicMock()

    # Make import raise ImportError for ocrmypdf
    def import_side_effect(name, *args, **kwargs):
        if name == "ocrmypdf":
            raise ImportError("No module named 'ocrmypdf'")
        return __import__(name, *args, **kwargs)

    mock_import.side_effect = import_side_effect

    output_path = sample_pdf.parent / "input_ocr.pdf"
    result = process_file(sample_pdf, output_path)

    assert result.status == "failed"
    assert "ocrmypdf" in result.error.lower() or "install" in result.error.lower()
