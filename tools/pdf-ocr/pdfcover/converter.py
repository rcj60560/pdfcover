"""Main entry point for PDF conversion."""

from pdfcover.scanner import scan_folder, ScanResult
from pdfcover.processor import process_file, ProcessResult
from pdfcover.config import DEFAULT_OUTPUT_SUFFIX


def convert_folder(
    folder_path: str,
    output_suffix: str = DEFAULT_OUTPUT_SUFFIX,
    recursive: bool = False
) -> list[dict]:
    """
    Scan a folder and convert all scanned PDFs to searchable PDFs.

    Args:
        folder_path: Path to folder containing PDFs
        output_suffix: Suffix for output files (default: "_ocr")
        recursive: Whether to process subfolders (default: False, not yet implemented)

    Returns:
        List of result dicts with keys: source, output, status, error

    Raises:
        FileNotFoundError: If folder_path does not exist
    """
    results = []

    # Scan folder for PDFs
    for scan_result in scan_folder(folder_path, output_suffix):
        if scan_result.status == "skipped":
            results.append({
                "source": str(scan_result.source),
                "output": str(scan_result.output),
                "status": "skipped",
                "error": None
            })
            continue

        # Process the PDF
        process_result = process_file(scan_result.source, scan_result.output)

        results.append({
            "source": str(process_result.source),
            "output": str(process_result.output),
            "status": process_result.status,
            "error": process_result.error
        })

    return results
