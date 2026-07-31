import pytest
from pdfcover.exceptions import PDFCoverError, OCRError, InvalidPDFError


def test_pdf_cover_error_is_exception():
    assert issubclass(PDFCoverError, Exception)


def test_ocr_error_is_pdf_cover_error():
    assert issubclass(OCRError, PDFCoverError)


def test_invalid_pdf_error_is_pdf_cover_error():
    assert issubclass(InvalidPDFError, PDFCoverError)


def test_exceptions_can_be_instantiated():
    err1 = PDFCoverError("base error")
    err2 = OCRError("ocr failed")
    err3 = InvalidPDFError("bad pdf")

    assert str(err1) == "base error"
    assert str(err2) == "ocr failed"
    assert str(err3) == "bad pdf"


def test_exceptions_can_be_raised_and_caught():
    with pytest.raises(PDFCoverError):
        raise PDFCoverError("test")

    with pytest.raises(OCRError):
        raise OCRError("ocr test")

    with pytest.raises(InvalidPDFError):
        raise InvalidPDFError("pdf test")
