"""抓取 BWF 世界排名（5 单项 × Top 50）→ out/rankings.json"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
BASE = "https://bwfworldtour.bwfbadminton.com"
CAT_IDS = {"ms": 57, "ws": 58, "md": 59, "wd": 60, "xd": 61}
DISCIPLINE_NAMES = {"ms": "男单", "ws": "女单", "md": "男双", "wd": "女双", "xd": "混双"}
OUT = Path(__file__).parent / "out"


def http_get(url: str, accept: str = "text/html,application/xhtml+xml") -> str:
    """带完整 UA 的 GET；Cloudflare 拦截时退避重试（短 UA 必 403，勿改 UA）。"""
    for attempt in range(3):
        r = requests.get(url, headers={"User-Agent": UA, "Accept": accept}, timeout=15)
        if r.status_code == 200 and "cloudflare" not in r.text[:2000].lower():
            return r.text
        time.sleep(2 ** attempt)
    raise RuntimeError(f"fetch failed: {url}")


def resolve_current_params() -> str:
    """解析当前周参数串（id/cat_id/ryear/week/...），统一 page_size=50。

    旧站 /rankings/ 无参 GET 返回 142B JS 跳转（document.location='...?参数'）；
    2026-08 实测改版：直接返回整页，参数内嵌于 rankings/?<query> 链接。两种形态均兼容。
    """
    html = http_get(BASE + "/rankings/")
    m = re.search(r"document\.location='([^']+)'", html)
    if m:
        query = m.group(1).split("?", 1)[1]
    else:
        m = re.search(r"rankings/\?([^\"']+)", html)
        if not m:
            raise RuntimeError("无法解析当前排名参数（页面结构可能已变化）")
        query = m.group(1)
    params = dict(pair.split("=", 1) for pair in query.split("&"))
    params["page_size"] = "50"  # 站点默认链接 page_size=25，Top 50 需显式指定
    return "&".join(f"{k}={v}" for k, v in params.items())


def parse_rankings_table(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_="rankings-table")
    if table is None:
        raise RuntimeError("未找到 rankings-table（选择器失配）")
    entries: list[dict] = []
    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 6:
            continue
        rank_m = re.search(r"\d+", tds[0].get_text())
        if not rank_m:
            continue
        country_el = tds[1].select_one(".country span")
        players = [a.get_text(strip=True) for a in tds[2].select(".player a")]
        change_m = re.search(r"-?\d+", tds[3].get_text())
        points_m = re.search(r"[\d,]+", tds[4].get_text())
        if not players:
            continue
        entries.append({
            "rank": int(rank_m.group()),
            "change": int(change_m.group()) if change_m else 0,
            "country": country_el.get_text(strip=True) if country_el else "",
            "player": " / ".join(players),
            "points": int(points_m.group().replace(",", "")) if points_m else 0,
        })
        if len(entries) >= 50:
            break
    return entries


def scrape_rankings() -> dict:
    base_q = resolve_current_params()
    q = dict(pair.split("=", 1) for pair in base_q.split("&"))
    disciplines = {}
    for key, cat_id in CAT_IDS.items():
        q["cat_id"] = str(cat_id)
        url = BASE + "/rankings/?" + "&".join(f"{k}={v}" for k, v in q.items())
        entries = parse_rankings_table(http_get(url))
        if len(entries) < 40:
            raise RuntimeError(f"{key} 只解析到 {len(entries)} 行（阈值 40），中止以防残缺数据")
        disciplines[key] = {"name": DISCIPLINE_NAMES[key], "entries": entries}
        time.sleep(2)  # 礼貌间隔
    return {
        "updatedAt": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "source": "bwfworldtour.bwfbadminton.com",
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
