import pytest
from pathlib import Path
from pdfcover.scanner import scan_folder, ScanResult


@pytest.fixture
def temp_folder_with_pdfs(tmp_path):
    """Create a temporary folder with mixed files."""
    (tmp_path / "doc1.pdf").write_bytes(b"%PDF-1.4")
    (tmp_path / "doc2.pdf").write_bytes(b"%PDF-1.4")
    (tmp_path / "doc1_ocr.pdf").write_bytes(b"%PDF-1.4")  # Already converted
    (tmp_path / "readme.txt").write_text("Not a PDF")
    (tmp_path / ".hidden").mkdir()
    (tmp_path / ".hidden" / "hidden.pdf").write_bytes(b"%PDF-1.4")
    return tmp_path


def test_scan_folder_finds_pdfs(temp_folder_with_pdfs):
    """Scanner should find PDF files in folder."""
    results = list(scan_folder(str(temp_folder_with_pdfs), "_ocr"))

    # doc1.pdf skipped (doc1_ocr.pdf exists)
    # doc1_ocr.pdf not scanned (it's an output file)
    # doc2.pdf pending (no output exists yet)
    pdf_names = {r.source.name for r in results if r.status == "pending"}
    assert pdf_names == {"doc2.pdf"}


def test_scan_folder_skips_existing_output(temp_folder_with_pdfs):
    """Scanner should skip files that already have _ocr version."""
    results = list(scan_folder(str(temp_folder_with_pdfs), "_ocr"))

    skipped = [r for r in results if r.status == "skipped"]
    assert len(skipped) == 1
    assert skipped[0].source.name == "doc1.pdf"


def test_scan_folder_handles_non_pdf_files(temp_folder_with_pdfs):
    """Scanner should ignore non-PDF files."""
    results = list(scan_folder(str(temp_folder_with_pdfs), "_ocr"))

    # readme.txt should not appear
    non_pdf = [r for r in results if r.source.name == "readme.txt"]
    assert len(non_pdf) == 0


def test_scan_folder_nonexistent_folder():
    """Scanner should raise FileNotFoundError for nonexistent folder."""
    with pytest.raises(FileNotFoundError):
        list(scan_folder("/nonexistent/folder", "_ocr"))


def test_scan_result_dataclass():
    """ScanResult should hold file path and output path."""
    result = ScanResult(
        source=Path("/path/doc.pdf"),
        output=Path("/path/doc_ocr.pdf"),
        status="pending"
    )
    assert result.source.name == "doc.pdf"
    assert result.output.name == "doc_ocr.pdf"
    assert result.status == "pending"
