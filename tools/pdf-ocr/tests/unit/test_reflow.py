"""Unit tests for the single-column reflow module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pdfcover.reflow import (
    ReflowResult,
    _Word,
    _detect_columns,
    _group_chars_to_words,
    reflow_pdf,
)


class _FakeChar:
    """Minimal stand-in for pdfminer's LTChar."""

    def __init__(self, x0, y0, x1, y1, text):
        self.x0 = x0
        self.y0 = y0
        self.x1 = x1
        self.y1 = y1
        self._text = text

    def get_text(self):
        return self._text


def _words_in_band(start_x, end_x, tops, text="w"):
    """Build _Word objects that continuously tile an x-band at given y tops.

    Mimics real text, where adjacent words cover the line with no horizontal
    gaps, so the coverage histogram is dense inside a column and empty in a
    gutter.
    """
    words = []
    for top in tops:
        x = start_x
        while x < end_x:
            x1 = min(x + 12, end_x)
            words.append(_Word(float(x), float(x1), float(top), text))
            x = x1
    return words


# --- column detection ------------------------------------------------------

def test_detect_columns_single_column():
    """A page whose words span the full width yields one column."""
    words = _words_in_band(40, 500, range(700, 100, -15))
    cols = _detect_columns(words, page_width=540.0)
    assert len(cols) == 1


def test_detect_columns_two_columns():
    """A clear central gutter splits the page into two columns."""
    words = _words_in_band(40, 240, range(700, 100, -15))
    words += _words_in_band(300, 500, range(700, 100, -15))
    cols = _detect_columns(words, page_width=540.0)
    assert len(cols) == 2
    # Boundary sits inside the gutter, between the two bands.
    boundary = cols[0][1]
    assert 240 < boundary < 300


def test_detect_columns_four_columns():
    """Three gutters yield four columns of roughly equal weight."""
    bands = [(40, 150), (180, 290), (320, 430), (460, 520)]
    tops = list(range(700, 100, -15))
    words = []
    for start_x, end_x in bands:
        words += _words_in_band(start_x, end_x, tops)
    cols = _detect_columns(words, page_width=540.0)
    assert len(cols) == 4


# --- word grouping ---------------------------------------------------------

def test_group_chars_to_words_uses_per_word_top():
    """A word's top must come from its own first char, not the line's leftmost.

    Regression guard: previously the whole line's leftmost char supplied the
    top for every word, which scrambled reading order on multi-column pages.
    """
    chars = [
        _FakeChar(10, 90, 18, 100, "A"),
        _FakeChar(20, 90, 28, 100, "B"),
        # big horizontal gap -> new word, at a slightly different baseline
        _FakeChar(100, 94, 108, 104, "C"),
        _FakeChar(110, 94, 118, 104, "D"),
    ]
    words = _group_chars_to_words(chars)
    texts = {w.text: w.top for w in words}
    assert texts["AB"] == 100
    assert texts["CD"] == 104  # its own baseline, not the line's leftmost (100)


def test_group_chars_to_words_splits_on_space():
    """A space character separates two words on the same line."""
    chars = [
        _FakeChar(10, 90, 18, 100, "h"),
        _FakeChar(18, 90, 26, 100, "i"),
        _FakeChar(26, 90, 30, 100, " "),
        _FakeChar(40, 90, 48, 100, "y"),
        _FakeChar(48, 90, 56, 100, "o"),
    ]
    words = [w.text for w in _group_chars_to_words(chars)]
    assert words == ["hi", "yo"]


# --- reflow_pdf error paths ------------------------------------------------

@patch("pdfcover.reflow.PdfReader")
def test_reflow_pdf_rejects_inverted_range(mock_reader):
    """reflow_pdf rejects ranges where start is greater than end."""
    mock_reader.return_value.pages = ["p"] * 10
    result = reflow_pdf("in.pdf", "out.txt", start_page=6, end_page=4)
    assert result.status == "failed"
    assert "起始页" in result.error


@patch("pdfcover.reflow.PdfReader")
def test_reflow_pdf_rejects_pages_beyond_pdf(mock_reader):
    """reflow_pdf rejects ranges beyond the PDF page count."""
    mock_reader.return_value.pages = ["p"] * 5
    result = reflow_pdf("in.pdf", "out.txt", start_page=1, end_page=9)
    assert result.status == "failed"
    assert result.page_count == 5


@patch("pdfcover.reflow.PdfReader", side_effect=RuntimeError("boom"))
def test_reflow_pdf_handles_unreadable_pdf(mock_reader):
    """reflow_pdf reports a failure when the PDF cannot be opened."""
    result = reflow_pdf("in.pdf", "out.txt")
    assert result.status == "failed"
    assert "PDF" in result.error


# --- end-to-end on a generated multi-column PDF ---------------------------

@pytest.fixture
def two_column_pdf(tmp_path):
    """Build a real 2-column PDF with fpdf2 (skipped if fpdf2 is absent)."""
    fpdf = pytest.importorskip("fpdf")
    path = tmp_path / "twocol.pdf"
    pdf = fpdf.FPDF(format="A4")
    pdf.set_auto_page_break(False)
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    # Left column, top to bottom.
    left_lines = ["alpha one", "bravo two", "charlie three"]
    right_lines = ["delta four", "echo five", "foxtrot six"]
    top = 40
    for line in left_lines:
        pdf.set_xy(15, top)
        pdf.cell(80, 8, line)
        top += 12
    top = 40
    for line in right_lines:
        pdf.set_xy(115, top)
        pdf.cell(80, 8, line)
        top += 12
    pdf.output(str(path))
    return path, left_lines, right_lines


def test_reflow_two_column_pdf_order(two_column_pdf, tmp_path):
    """The whole left column is emitted before the right column, in order."""
    path, left_lines, right_lines = two_column_pdf
    out = tmp_path / "out.txt"
    result = reflow_pdf(path, out, start_page=1, end_page=1)
    assert result.status == "success"
    text = result.text
    assert "alpha one" in text and "foxtrot six" in text

    # Last left-column line must precede the first right-column line.
    assert text.index("charlie three") < text.index("delta four")
    # And the left column itself stays in top-to-bottom order.
    assert text.index("alpha one") < text.index("bravo two") < text.index("charlie three")

    assert out.exists()
    assert out.read_text(encoding="utf-8") == result.text
