"""抓取 BWF 世界巡回赛赛程（extranet-lv JSON API）→ out/schedule.json"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import requests

from scrape_rankings import UA, OUT

API = "https://extranet-lv.bwfbadminton.com/api/vue-grouped-year-tournaments"
REFERER = "https://bwfworldtour.bwfbadminton.com/calendar/"
LEVELS = [
    ("World Tour Finals", "finals"),
    ("Super 1000", "super1000"),
    ("Super 750", "super750"),
    ("Super 500", "super500"),
    ("Super 300", "super300"),
]


def level_from_category(category: str) -> str:
    low = category.lower()
    # Grade 1 顶级大赛（世锦赛/汤尤杯）→ major；Junior 级别（世青赛/青奥）仍不入列
    if "grade 1" in low and "junior" not in low:
        return "major"
    for needle, level in LEVELS:
        if needle.lower() in low:
            return level
    return "other"


def parse_schedule(payload: dict, year: int) -> dict:
    tournaments = []
    for month in payload.get("results", []):
        for t in month.get("tournaments", []):
            level = level_from_category(t.get("category", ""))
            if level == "other":
                continue  # 只收 World Tour + Grade 1 大赛（spec §2，2026-08-18 扩 major）
            prize = str(t.get("prize_money", "0")).replace(",", "")
            tournaments.append({
                "name": t["name"],
                "startDate": t["start_date"][:10],
                "endDate": t["end_date"][:10],
                "city": t.get("location", ""),
                "level": level,
                "prizeMoney": int(prize) if prize.isdigit() else 0,
            })
    tournaments.sort(key=lambda x: x["startDate"])
    return {
        "updatedAt": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "year": year,
        "tournaments": tournaments,
    }


def scrape_schedule(year: int) -> dict:
    r = requests.get(
        API,
        params={"year": year},
        headers={"User-Agent": UA, "Accept": "application/json", "Referer": REFERER},
        timeout=15,
    )
    r.raise_for_status()
    return parse_schedule(r.json(), year)


def main(year: int | None = None) -> None:
    year = year or datetime.now().year
    data = scrape_schedule(year)
    if len(data["tournaments"]) < 20:
        raise RuntimeError(f"只解析到 {len(data['tournaments'])} 站（阈值 20），中止")
    OUT.mkdir(exist_ok=True)
    (OUT / "schedule.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"OK schedule.json: {year} 年 {len(data['tournaments'])} 站")


if __name__ == "__main__":
    main()
