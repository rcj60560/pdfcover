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
    # Grade 1 顶级大赛（世锦赛/汤尤杯）入列 major；Junior 级别（世青赛/青奥）不入
    assert level_from_category("Grade 1 – Individual Tournaments") == "major"
    assert level_from_category("Grade 1 – Team Tournaments") == "major"
    assert level_from_category("Grade 1 – Individual Junior Tournaments") == "other"
    assert level_from_category("Grade 1 – Junior Team Tournaments") == "other"


def test_parse_filters_and_sorts():
    payload = json.loads((FIX / "schedule_api.json").read_text(encoding="utf-8"))
    data = parse_schedule(payload, 2026)
    names = [t["name"] for t in data["tournaments"]]
    # 非 World Tour 且非 Grade 1 大赛的过滤（含 Junior Grade 1）；按 startDate 升序
    assert names == [
        "PETRONAS Malaysia Open 2026",
        "BWF World Championships 2026",
        "HSBC BWF World Tour Finals 2026",
    ]
    first = data["tournaments"][0]
    assert first["level"] == "super1000"
    assert first["prizeMoney"] == 1450000
    assert first["startDate"] == "2026-01-06"
    worlds = data["tournaments"][1]
    assert worlds["level"] == "major"
    assert worlds["prizeMoney"] == 0  # prize_money null → 0
    assert worlds["startDate"] == "2026-08-17"
    assert worlds["code"] == "B671FB97-491C-46D3-982F-56525168C3AA"
    assert worlds["hasLiveScores"] is True
    # 旧字段缺 code/has_live_scores 时回退 null/False（向后兼容）
    assert data["tournaments"][0]["code"] is None
    assert data["tournaments"][0]["hasLiveScores"] is False
    assert data["year"] == 2026
