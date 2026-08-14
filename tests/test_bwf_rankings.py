import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "tools" / "bwf-data"))
from scrape_rankings import parse_rankings_table

FIX = Path(__file__).parent / "fixtures"


def test_parse_singles():
    entries = parse_rankings_table((FIX / "rankings_ms.html").read_text(encoding="utf-8"))
    assert len(entries) == 3
    assert entries[0] == {"rank": 1, "change": 0, "country": "TPE",
                          "player": "CHOU Tien Chen", "points": 67710}
    assert entries[1]["points"] == 30900


def test_negative_change_keeps_sign():
    entries = parse_rankings_table((FIX / "rankings_ms.html").read_text(encoding="utf-8"))
    assert entries[2]["change"] == -5


def test_doubles_joined_with_slash():
    entries = parse_rankings_table((FIX / "rankings_xd.html").read_text(encoding="utf-8"))
    assert entries[0]["player"] == "WANG Chi-Lin / LEE Jhe-Huei"
