import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "tools" / "bwf-data"))
from scrape_schedule import parse_schedule, level_from_category

FIX = Path(__file__).parent / "fixtures"


def test_level_mapping():
    assert level_from_category("HSBC BWF World Tour Super 1000") == "super1000"
    assert level_from_category("HSBC BWF World Tour Super 750") == "super750"
    assert level_from_category("HSBC BWF World Tour Finals") == "finals"
    assert level_from_category("BWF International Challenge") == "other"


def test_parse_filters_and_sorts():
    payload = json.loads((FIX / "schedule_api.json").read_text(encoding="utf-8"))
    data = parse_schedule(payload, 2026)
    names = [t["name"] for t in data["tournaments"]]
    # 非 World Tour 被过滤；按 startDate 升序
    assert names == ["PETRONAS Malaysia Open 2026", "HSBC BWF World Tour Finals 2026"]
    first = data["tournaments"][0]
    assert first["level"] == "super1000"
    assert first["prizeMoney"] == 1450000
    assert first["startDate"] == "2026-01-06"
    assert data["year"] == 2026
