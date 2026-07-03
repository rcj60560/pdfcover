from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

from pdfcover.splitter import SplitResult, extract_page_range


def test_split_result_dataclass():
    """SplitResult should hold page extraction result data."""
    result = SplitResult(
        source=Path("/path/source.pdf"),
        output=Path("/path/output.pdf"),
        status="success",
        page_count=80,
    )
    assert result.status == "success"
    assert result.page_count == 80


def test_extract_page_range_rejects_invalid_range():
    """extract_page_range should reject ranges where start is greater than end."""
    result = extract_page_range("input.pdf", "output.pdf", 60, 50)
    assert result.status == "failed"
    assert "起始页" in result.error


@patch("pdfcover.splitter.open", new_callable=mock_open)
@patch("pdfcover.splitter.PdfWriter")
@patch("pdfcover.splitter.PdfReader")
def test_extract_page_range_success(mock_reader, mock_writer, mock_file):
    """extract_page_range should write the requested inclusive page range."""
    reader = MagicMock()
    reader.pages = ["p1", "p2", "p3", "p4", "p5"]
    mock_reader.return_value = reader

    writer = MagicMock()
    mock_writer.return_value = writer

    result = extract_page_range("input.pdf", "output.pdf", 2, 4)

    assert result.status == "success"
    assert result.page_count == 5
    assert writer.add_page.call_args_list[0].args[0] == "p2"
    assert writer.add_page.call_args_list[2].args[0] == "p4"
    writer.write.assert_called_once()


@patch("pdfcover.splitter.PdfReader")
def test_extract_page_range_rejects_pages_beyond_pdf(mock_reader):
    """extract_page_range should reject ranges beyond the PDF page count."""
    reader = MagicMock()
    reader.pages = ["p1", "p2"]
    mock_reader.return_value = reader

    result = extract_page_range("input.pdf", "output.pdf", 1, 3)

    assert result.status == "failed"
    assert result.page_count == 2
