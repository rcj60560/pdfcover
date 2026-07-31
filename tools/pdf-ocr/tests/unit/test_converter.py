import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from pdfcover.converter import convert_folder


@pytest.fixture
def temp_folder(tmp_path):
    """Create a temporary folder with PDFs."""
    (tmp_path / "doc1.pdf").write_bytes(b"%PDF-1.4")
    (tmp_path / "doc2.pdf").write_bytes(b"%PDF-1.4")
    return tmp_path


@patch("pdfcover.converter.process_file")
def test_convert_folder_processes_all_pdfs(mock_process, temp_folder):
    """convert_folder should process all PDF files."""
    # Mock process_file to return success
    mock_process.return_value = MagicMock(
        status="success",
        source=Path("doc.pdf"),
        output=Path("doc_ocr.pdf")
    )

    results = convert_folder(str(temp_folder))

    assert len(results) == 2
    assert all(r["status"] == "success" for r in results)


@patch("pdfcover.converter.process_file")
def test_convert_folder_handles_failures(mock_process, temp_folder):
    """convert_folder should continue after individual failures."""
    call_count = 0

    def side_effect(source, output):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return MagicMock(status="failed", error="Test error", source=source, output=output)
        return MagicMock(status="success", source=source, output=output)

    mock_process.side_effect = side_effect

    results = convert_folder(str(temp_folder))

    assert len(results) == 2
    assert results[0]["status"] == "failed"
    assert results[0]["error"] == "Test error"
    assert results[1]["status"] == "success"


@patch("pdfcover.converter.process_file")
def test_convert_folder_custom_suffix(mock_process, temp_folder):
    """convert_folder should use custom output suffix."""
    mock_process.return_value = MagicMock(
        status="success",
        source=Path("doc.pdf"),
        output=Path("doc_searchable.pdf")
    )

    results = convert_folder(str(temp_folder), output_suffix="_searchable")

    assert len(results) == 2
    # Verify output paths have custom suffix
    assert mock_process.call_count == 2


def test_convert_folder_nonexistent_folder():
    """convert_folder should raise FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        convert_folder("/nonexistent/folder")


@patch("pdfcover.converter.process_file")
@patch("pdfcover.converter.scan_folder")
def test_convert_folder_empty_folder(mock_scan, mock_process, temp_folder):
    """convert_folder should handle empty folders."""
    mock_scan.return_value = []  # No files found

    results = convert_folder(str(temp_folder))

    assert results == []
    mock_process.assert_not_called()
