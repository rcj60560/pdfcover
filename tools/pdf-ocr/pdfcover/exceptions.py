"""Custom exceptions for PDFCover."""


class PDFCoverError(Exception):
    """Base exception for PDFCover errors."""
    pass


class OCRError(PDFCoverError):
    """Exception raised when OCR processing fails."""
    pass


class InvalidPDFError(PDFCoverError):
    """Exception raised when a PDF file is invalid or cannot be read."""
    pass
