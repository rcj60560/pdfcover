"""PDF file scanning logic."""

from dataclasses import dataclass
from pathlib import Path
from typing import Generator


@dataclass
class ScanResult:
    """Result of scanning a single PDF file."""
    source: Path
    output: Path
    status: str  # "pending", "skipped"


def scan_folder(
    folder_path: str,
    output_suffix: str
) -> Generator[ScanResult, None, None]:
    """
    Scan a folder for PDF files.

    Args:
        folder_path: Path to folder containing PDFs
        output_suffix: Suffix for output files (e.g., "_ocr")

    Yields:
        ScanResult for each PDF file found

    Raises:
        FileNotFoundError: If folder_path does not exist
    """
    folder = Path(folder_path)

    if not folder.exists():
        raise FileNotFoundError(f"Folder not found: {folder_path}")

    if not folder.is_dir():
        raise NotADirectoryError(f"Not a directory: {folder_path}")

    # Get all PDF files (not hidden, not directories, not already output files)
    pdf_files = [
        f for f in folder.iterdir()
        if f.is_file()
        and f.suffix.lower() == ".pdf"
        and not f.name.startswith(".")
        and not f.stem.endswith(output_suffix)  # Skip files already ending with suffix
    ]

    for pdf_file in pdf_files:
        output_file = pdf_file.with_name(f"{pdf_file.stem}{output_suffix}{pdf_file.suffix}")

        # Skip if output file already exists and is readable
        if output_file.exists():
            yield ScanResult(source=pdf_file, output=output_file, status="skipped")
        else:
            yield ScanResult(source=pdf_file, output=output_file, status="pending")
