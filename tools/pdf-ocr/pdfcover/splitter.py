"""PDF page range extraction."""

from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader, PdfWriter


@dataclass
class SplitResult:
    """Result of extracting a page range from a PDF file."""

    source: Path
    output: Path
    status: str
    error: str | None = None
    page_count: int | None = None


def extract_page_range(
    source: str | Path,
    output: str | Path,
    start_page: int,
    end_page: int,
) -> SplitResult:
    """Extract an inclusive 1-based page range from a PDF file."""

    source_path = Path(source)
    output_path = Path(output)

    if start_page < 1 or end_page < 1:
        return SplitResult(source_path, output_path, "failed", "页码必须从 1 开始")

    if start_page > end_page:
        return SplitResult(source_path, output_path, "failed", "起始页不能大于结束页")

    try:
        reader = PdfReader(str(source_path))
        total_pages = len(reader.pages)

        if start_page > total_pages:
            return SplitResult(
                source_path,
                output_path,
                "failed",
                f"起始页超过 PDF 总页数（{total_pages} 页）",
                total_pages,
            )

        if end_page > total_pages:
            return SplitResult(
                source_path,
                output_path,
                "failed",
                f"结束页超过 PDF 总页数（{total_pages} 页）",
                total_pages,
            )

        writer = PdfWriter()
        for page_index in range(start_page - 1, end_page):
            writer.add_page(reader.pages[page_index])

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as output_file:
            writer.write(output_file)

        return SplitResult(source_path, output_path, "success", page_count=total_pages)
    except Exception as exc:
        return SplitResult(source_path, output_path, "failed", f"PDF 截取失败：{exc}")
