import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "tools" / "bwf-data"))
from scrape_rankings import parse_rankings_payload, publication_id_from_weeks

FIX = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def test_parse_singles():
    entries = parse_rankings_payload(_load("rankings_table_ms.json"))
    assert entries[0] == {"rank": 1, "change": 0, "country": "CHN",
                          "player": "SHI Yu Qi", "points": 94255}
    assert entries[1]["country"] == "THA"
    assert entries[1]["change"] == 1
    assert entries[1]["points"] == 91215


def test_negative_change_keeps_sign():
    entries = parse_rankings_payload(_load("rankings_table_ms.json"))
    assert entries[2]["change"] == -2


def test_unmapped_country_falls_back_to_full_name():
    entries = parse_rankings_payload(_load("rankings_table_ms.json"))
    assert entries[2]["country"] == "Atlantis"


def test_doubles_joined_with_slash():
    entries = parse_rankings_payload(_load("rankings_table_xd.json"))
    assert entries[0]["player"] == "FENG Yan Zhe / HUANG Dong Ping"
    assert entries[0]["points"] == 90110


def test_week_key_to_publication_id():
    weeks = [
        {"key": "2026-34-4435", "date": "2026-08-18 00:00:00"},
        {"key": "2026-33-4400", "date": "2026-08-11 00:00:00"},
    ]
    # API 只认纯数字 publicationId（带日期前缀的 key 会返回空表）
    assert publication_id_from_weeks(weeks) == "4435"
