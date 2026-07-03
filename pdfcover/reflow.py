"""Reflow a multi-column PDF text layer into single-column reading order.

OCR'd PDFs (e.g. Cambridge IELTS transcripts) often carry an invisible text
layer whose reading order follows the page geometry. For multi-column pages
the copy/extract order jumps across columns and even interleaves words. This
module rebuilds the reading order from character positions: it detects the
vertical gutters between columns on each page and emits text column by column,
top to bottom within each column.
"""

from dataclasses import dataclass
from pathlib import Path

from pdfminer.high_level import extract_pages
from pdfminer.layout import LAParams, LTChar, LTContainer
from pypdf import PdfReader

# A "line" groups characters whose top edge is within this many points.
_LINE_TOLERANCE = 6.0
# Horizontal gap (points) above which adjacent chars on the same line split
# into separate words.
_WORD_GAP = 3.0
# Resolution of the coverage histogram used to find column gutters.
_HISTOGRAM_BINS = 80
# A bin counts as part of a gutter when its coverage is below this fraction of
# the busiest bin on the page.
_GUTTER_DENSITY = 0.08
# A gutter must be at least this fraction of the page width to count as a real
# column separator.
_MIN_GUTTER_FRAC = 0.02
# Columns holding fewer than this share of a page's words are treated as page
# margins (or stray fragments) and merged into their neighbour.
_MIN_COLUMN_SHARE = 0.02
# Cap on the number of characters returned inline (the full text is always
# written to disk); guards the JSON payload for very large documents.
_INLINE_TEXT_LIMIT = 30000


@dataclass
class ReflowResult:
    """Result of reflwoing a PDF into single-column text."""

    source: Path
    output: Path
    status: str  # "success", "failed"
    error: str | None = None
    page_count: int | None = None
    text: str = ""
    truncated: bool = False


@dataclass
class _Word:
    x0: float
    x1: float
    top: float  # higher = further up the page
    text: str


def _iter_chars(node) -> list[LTChar]:
    """Recursively collect every LTChar under a layout node."""
    chars: list[LTChar] = []
    for child in node:
        if isinstance(child, LTChar):
            chars.append(child)
        elif isinstance(child, LTContainer):
            chars.extend(_iter_chars(child))
    return chars


def _group_chars_to_words(chars: list[LTChar]) -> list[_Word]:
    """Group characters into words, respecting line breaks and word gaps."""
    if not chars:
        return []

    # Sort top-to-bottom (pdfminer y grows upward, so larger top = higher),
    # then left-to-right.
    chars = sorted(chars, key=lambda c: (-c.y1, c.x0))

    words: list[_Word] = []
    line: list[LTChar] = []
    line_top: float | None = None

    def flush(line_chars: list[LTChar]):
        line_chars.sort(key=lambda c: c.x0)
        text = ""
        x0 = x1 = None
        top = None  # y1 of this word's own first char, not the line's
        prev = None
        for c in line_chars:
            ch = c.get_text()
            gap = (c.x0 - prev.x1) if prev is not None else 0.0
            if ch == " " or (prev is not None and gap > _WORD_GAP):
                if text.strip():
                    words.append(_Word(x0, x1, top, text))
                text = ""
                x0 = None
                top = None
            if ch != " ":
                if x0 is None:
                    x0 = c.x0
                    top = c.y1
                x1 = c.x1
                text += ch
            prev = c
        if text.strip():
            words.append(_Word(x0, x1, top, text))

    for c in chars:
        if line_top is None or abs(c.y1 - line_top) <= _LINE_TOLERANCE:
            line.append(c)
            if line_top is None:
                line_top = c.y1
        else:
            flush(line)
            line = [c]
            line_top = c.y1
    flush(line)
    return words


def _detect_columns(words: list[_Word], page_width: float) -> list[tuple[float, float]]:
    """Detect column boundaries from the horizontal word-coverage histogram.

    Gutters are sought only within the actual content extent (between the
    leftmost and rightmost word), so page margins never become their own
    columns. Columns holding almost no words (stray fragments) are folded into
    a neighbour. Returns a list of (x_start, x_end) regions, left to right.
    """
    if not words:
        return [(0.0, page_width)]

    content_x0 = min(w.x0 for w in words)
    content_x1 = max(w.x1 for w in words)
    span = content_x1 - content_x0
    if span <= 1:
        return [(content_x0, content_x1)]

    histogram = [0.0] * _HISTOGRAM_BINS
    for w in words:
        start = max(0, int((w.x0 - content_x0) / span * _HISTOGRAM_BINS))
        end = min(_HISTOGRAM_BINS - 1, int((w.x1 - content_x0) / span * _HISTOGRAM_BINS))
        for b in range(start, end + 1):
            histogram[b] += 1

    peak = max(histogram) or 1.0
    threshold = peak * _GUTTER_DENSITY
    min_bins = max(2, int(_MIN_GUTTER_FRAC * _HISTOGRAM_BINS))

    # Find contiguous low-coverage runs = gutter centres, within content.
    gutters: list[float] = []
    b = 0
    while b < _HISTOGRAM_BINS:
        if histogram[b] < threshold:
            run_start = b
            while b < _HISTOGRAM_BINS and histogram[b] < threshold:
                b += 1
            run_end = b
            if run_end - run_start >= min_bins:
                mid = (run_start + run_end - 1) / 2
                gutters.append(content_x0 + mid / _HISTOGRAM_BINS * span)
        else:
            b += 1

    bounds = [content_x0, *gutters, content_x1]
    columns = [(bounds[i], bounds[i + 1]) for i in range(len(bounds) - 1)]

    # Fold columns holding almost no words into an adjacent column. A run of
    # leading marginal columns is absorbed into the first real column's left
    # edge; a trailing run extends the last real column's right edge.
    total = len(words)
    min_count = max(1.0, total * _MIN_COLUMN_SHARE)
    counts = [
        sum(1 for w in words if c0 <= (w.x0 + w.x1) / 2 < c1) for c0, c1 in columns
    ]
    kept: list[list[float]] = []
    pending_left: float | None = None
    for (c0, c1), count in zip(columns, counts):
        if count >= min_count:
            left = c0 if pending_left is None else pending_left
            kept.append([left, c1])
            pending_left = None
        else:
            if pending_left is None:
                pending_left = c0
            if kept:
                kept[-1][1] = c1  # trailing marginal: extend previous
    if not kept:
        return [(content_x0, content_x1)]
    return [(a, b) for a, b in kept]


def _reflow_page(page) -> str:
    """Return the single-column text for one page."""
    chars = _iter_chars(page)
    words = _group_chars_to_words(chars)
    if not words:
        return ""

    columns = _detect_columns(words, page.width)
    buckets: list[list[_Word]] = [[] for _ in columns]
    for w in words:
        center = (w.x0 + w.x1) / 2
        for i, (c0, c1) in enumerate(columns):
            if c0 <= center < c1:
                buckets[i].append(w)
                break

    lines: list[str] = []
    for i, bucket in enumerate(buckets):
        if not bucket:
            continue
        if lines:
            lines.append("")
        bucket.sort(key=lambda w: (-w.top, w.x0))
        run: list[_Word] = []
        run_top: float | None = None
        for w in bucket:
            if run_top is None or abs(w.top - run_top) <= _LINE_TOLERANCE:
                run.append(w)
                if run_top is None:
                    run_top = w.top
            else:
                run.sort(key=lambda w: w.x0)
                lines.append(" ".join(word.text for word in run))
                run = [w]
                run_top = w.top
        if run:
            run.sort(key=lambda w: w.x0)
            lines.append(" ".join(word.text for word in run))
    return "\n".join(lines)


def reflow_pdf(
    source: str | Path,
    output: str | Path,
    start_page: int | None = None,
    end_page: int | None = None,
) -> ReflowResult:
    """Reflow a PDF's text layer into single-column reading order.

    Args:
        source: Path to the source PDF (must already have a text layer; OCR
            scanned-only PDFs first).
        output: Path to the ``.txt`` file to write.
        start_page: Inclusive 1-based first page (default 1).
        end_page: Inclusive 1-based last page (default last page).

    Returns:
        ReflowResult with status, full text, and page count.
    """
    source_path = Path(source)
    output_path = Path(output)

    try:
        total_pages = len(PdfReader(str(source_path)).pages)
    except Exception as exc:
        return ReflowResult(source_path, output_path, "failed", f"无法读取 PDF：{exc}")

    first = 1 if start_page is None else start_page
    last = total_pages if end_page is None else end_page

    if first < 1 or last < 1:
        return ReflowResult(source_path, output_path, "failed", "页码必须从 1 开始", total_pages)
    if first > last:
        return ReflowResult(source_path, output_path, "failed", "起始页不能大于结束页", total_pages)
    if first > total_pages:
        return ReflowResult(
            source_path, output_path, "failed", f"起始页超过 PDF 总页数（{total_pages} 页）", total_pages
        )
    if last > total_pages:
        return ReflowResult(
            source_path, output_path, "failed", f"结束页超过 PDF 总页数（{total_pages} 页）", total_pages
        )

    try:
        page_numbers = list(range(first - 1, last))
        pages = extract_pages(str(source_path), page_numbers=page_numbers, laparams=LAParams())

        chunks: list[str] = []
        for index, page in enumerate(pages):
            body = _reflow_page(page)
            if body:
                chunks.append(f"===== 第 {first + index} 页 =====\n{body}")

        text = "\n\n".join(chunks)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text, encoding="utf-8")

        truncated = len(text) > _INLINE_TEXT_LIMIT
        return ReflowResult(
            source_path,
            output_path,
            "success",
            page_count=total_pages,
            text=text if not truncated else text[:_INLINE_TEXT_LIMIT],
            truncated=truncated,
        )
    except Exception as exc:
        return ReflowResult(source_path, output_path, "failed", f"整理失败：{exc}", total_pages)
