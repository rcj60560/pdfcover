import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "tools" / "bwf-data"))
from preview_gen import build_page

RANKINGS = {"updatedAt": "2026-08-14T09:00:00+08:00", "disciplines": {
    "ms": {"name": "男单", "entries": [{"rank": 1, "change": 0, "country": "TPE", "player": "CHOU Tien Chen", "points": 67710}]}}}
SCHEDULE = {"updatedAt": "2026-08-14T09:00:00+08:00", "year": 2026, "tournaments": [
    {"name": "LI-NING China Masters 2026", "startDate": "2026-09-01", "endDate": "2026-09-06",
     "city": "Shenzhen", "level": "super750", "prizeMoney": 1150000}]}


def test_preview_contains_data():
    html = build_page(RANKINGS, SCHEDULE)
    assert "CHOU Tien Chen" in html
    assert "LI-NING China Masters 2026" in html
    assert "2026-08-14" in html
    assert html.startswith("<!DOCTYPE html>")
