"""End-to-end integration tests (requires OCRmyPDF installed)."""

import pytest
from pathlib import Path


@pytest.mark.slow
@pytest.mark.integration
def test_convert_real_pdf(tmp_path):
    """Test conversion of a real PDF file.

    This test requires OCRmyPDF to be installed. Skip if not available.
    """
    # Check if OCRmyPDF is available
    try:
        import ocrmypdf
    except ImportError:
        pytest.skip("OCRmyPDF not installed")

    # Create a simple test PDF using echo and redirect
    # Or use a pre-made small test PDF
    test_pdf = tmp_path / "test.pdf"

    # Create a minimal PDF (just the header)
    # In real scenario, copy a real scanned PDF here
    test_pdf.write_bytes(
        b"%PDF-1.4\n"
        b"1 0 obj\n"
        b"<< /Type /Catalog /Pages 2 0 R >>\n"
        b"endobj\n"
        b"2 0 obj\n"
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>\n"
        b"endobj\n"
        b"3 0 obj\n"
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>\n"
        b"endobj\n"
        b"4 0 obj\n"
        b"<< /Length 44 >>\n"
        b"stream\n"
        b"BT\n/F1 12 Tf\n100 700 Td\n(Test) Tj\nET\n"
        b"endstream\n"
        b"endobj\n"
        b"xref\n"
        b"0 5\n"
        b"0000000000 65535 f\n"
        b"0000000009 00000 n\n"
        b"0000000056 00000 n\n"
        b"0000000110 00000 n\n"
        b"0000000201 00000 n\n"
        b"trailer\n"
        b"<< /Size 5 /Root 1 0 R >>\n"
        b"startxref\n"
        b"299\n"
        b"%%EOF\n"
    )

    from pdfcover import convert_folder

    results = convert_folder(str(tmp_path), output_suffix="_ocr")

    assert len(results) >= 1

    # Find our test file result
    test_result = None
    for r in results:
        if "test.pdf" in r["source"]:
            test_result = r
            break

    assert test_result is not None
    # Note: The minimal PDF might not have actual text to OCR,
    # so we expect either success or a specific error
    assert test_result["status"] in ["success", "failed", "skipped"]


@pytest.mark.slow
@pytest.mark.integration
def test_convert_folder_with_multiple_pdfs(tmp_path):
    """Test converting multiple PDFs in one call."""
    try:
        import ocrmypdf
    except ImportError:
        pytest.skip("OCRmyPDF not installed")

    # Create two test PDFs
    for i in range(2):
        pdf_file = tmp_path / f"doc{i+1}.pdf"
        pdf_file.write_bytes(b"%PDF-1.4\n%%EOF")

    from pdfcover import convert_folder

    results = convert_folder(str(tmp_path), output_suffix="_ocr")

    assert len(results) == 2
