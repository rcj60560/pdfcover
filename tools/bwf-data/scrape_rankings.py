"""抓取 BWF 世界排名（BWF World Rankings，5 单项 × Top 50）→ out/rankings.json

数据源：extranet-lv JSON API（BWF Fansite bwfbadminton.com/rankings 同源）。
rankId=2 才是正式世界排名；2026-08-18 前误用 bwfworldtour 站 /rankings/ 页面，
那是 HSBC Race to Guangzhou 积分榜（rankId=9），排序与积分完全不同。
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
API = "https://extranet-lv.bwfbadminton.com/api"
RANK_ID = 2  # 1=世青排名 2=世界排名 3=团体排名 9=Race to Guangzhou 14=残奥排名
CAT_IDS = {"ms": 6, "ws": 7, "md": 8, "wd": 9, "xd": 10}
DISCIPLINE_NAMES = {"ms": "男单", "ws": "女单", "md": "男双", "wd": "女双", "xd": "混双"}
OUT = Path(__file__).parent / "out"

# 国家全名 → BWF 三字码（与 BWF 站点展示一致）；未收录的回退全名，宁可长不可错
COUNTRY_CODES = {
    "China": "CHN", "Chinese Taipei": "TPE", "Korea": "KOR", "Japan": "JPN",
    "Indonesia": "INA", "India": "IND", "Thailand": "THA", "Malaysia": "MAS",
    "Denmark": "DEN", "France": "FRA", "Hong Kong China": "HKG", "Canada": "CAN",
    "USA": "USA", "Singapore": "SIN", "Scotland": "SCO", "Turkiye": "TUR",
    "Turkey": "TUR", "Bulgaria": "BUL", "Ukraine": "UKR", "Germany": "GER",
    "England": "ENG", "Spain": "ESP", "Ireland": "IRL", "Belgium": "BEL",
    "Vietnam": "VIE", "Czechia": "CZE", "Brazil": "BRA",
    # 常见但暂未进 Top50 的国家，防未来缺口
    "Sweden": "SWE", "Switzerland": "SUI", "Austria": "AUT", "Poland": "POL",
    "Italy": "ITA", "Netherlands": "NED", "Australia": "AUS", "New Zealand": "NZL",
    "Macau China": "MAC", "Philippines": "PHI", "Hungary": "HUN", "Croatia": "CRO",
    "Slovenia": "SLO", "Serbia": "SRB", "Slovakia": "SVK", "Finland": "FIN",
    "Norway": "NOR", "Portugal": "POR", "Greece": "GRE", "Romania": "ROU",
    "Wales": "WAL", "Estonia": "EST", "Latvia": "LAT", "Lithuania": "LTU",
    "Iceland": "ICE", "Israel": "ISR", "Egypt": "EGY", "South Africa": "RSA",
    "Algeria": "ALG", "Tunisia": "TUN", "Morocco": "MAR", "Nigeria": "NGR",
    "Ghana": "GHA", "Uganda": "UGA", "Kenya": "KEN", "Mauritius": "MRI",
    "Zambia": "ZAM", "Zimbabwe": "ZIM", "Botswana": "BOT", "Peru": "PER",
    "Mexico": "MEX", "Guatemala": "GUA", "Cuba": "CUB", "Chile": "CHI",
    "Argentina": "ARG", "Sri Lanka": "SRI", "Nepal": "NEP", "Pakistan": "PAK",
    "Laos": "LAO", "Myanmar": "MYA", "Cambodia": "CAM", "Azerbaijan": "AZE",
    "Georgia": "GEO", "Kazakhstan": "KAZ", "Uzbekistan": "UZB", "Iran": "IRI",
    "Mongolia": "MGL", "Luxembourg": "LUX",
}


def api_get(path: str, params: dict) -> dict:
    r = requests.get(API + path, params=params,
                     headers={"User-Agent": UA, "Accept": "application/json"}, timeout=15)
    r.raise_for_status()
    return r.json()


def publication_id_from_weeks(weeks: list[dict]) -> str:
    """最新一期周 key 形如 "2026-34-4435"；API 只认纯数字尾段（传整串会返回空表）。"""
    return str(weeks[0]["key"]).rsplit("-", 1)[-1]


def latest_publication_id() -> str:
    return publication_id_from_weeks(api_get("/vue-rankingweek", {"rankId": RANK_ID}))


def _strip_html(s: str | None) -> str:
    return re.sub(r"<[^>]+>", "", s or "").strip()


def parse_rankings_payload(payload: dict) -> list[dict]:
    """vue-rankingtable 响应 → 统一 entries（与旧 schema 兼容：rank/change/country/player/points）。"""
    entries: list[dict] = []
    for row in payload.get("results", {}).get("data", []):
        players = [_strip_html(row[side]["name_display_bold"])
                   for side in ("player1_model", "player2_model") if row.get(side)]
        country_model = row.get("p1_country_model") or {}
        entries.append({
            "rank": int(row.get("rank") or 0),
            "change": int(row.get("rank_change") or 0),
            "country": COUNTRY_CODES.get(country_model.get("name", ""), country_model.get("name", "")),
            "player": " / ".join(players),
            "points": int(float(row.get("points") or 0)),
        })
    return entries


def scrape_rankings() -> dict:
    pub = latest_publication_id()
    disciplines = {}
    for key, cat_id in CAT_IDS.items():
        payload = api_get("/vue-rankingtable", {
            "rankId": RANK_ID, "catId": cat_id, "publicationId": pub,
            "pageKey": 50, "page": 1,
        })
        entries = parse_rankings_payload(payload)
        if len(entries) < 40:
            raise RuntimeError(f"{key} 只解析到 {len(entries)} 行（阈值 40），中止以防残缺数据")
        disciplines[key] = {"name": DISCIPLINE_NAMES[key], "entries": entries}
        time.sleep(2)  # 礼貌间隔
    return {
        "updatedAt": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "source": "extranet-lv.bwfbadminton.com · BWF World Rankings",
        "disciplines": disciplines,
    }


def main() -> None:
    OUT.mkdir(exist_ok=True)
    data = scrape_rankings()
    (OUT / "rankings.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    total = sum(len(d["entries"]) for d in data["disciplines"].values())
    print(f"OK rankings.json: 5 单项共 {total} 条")


if __name__ == "__main__":
    main()
