"""生成自包含预览页 out/preview.html（数据内联，双击即开，浏览器肉眼校验）"""
from __future__ import annotations

import json
from pathlib import Path

from scrape_rankings import OUT

PAGE = """<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<title>BWF 数据预览</title>
<style>
body{font-family:"Microsoft YaHei",sans-serif;background:#F4F7F5;margin:0;padding:20px;max-width:900px}
h1{background:linear-gradient(135deg,#00A868,#0084C6);-webkit-background-clip:text;background-clip:text;color:transparent;font-size:22px}
small{color:#7C8F85}
.tabs{display:flex;gap:8px;margin:12px 0;flex-wrap:wrap}
.tab{padding:6px 14px;border-radius:999px;background:#fff;cursor:pointer;font-size:13px}
.tab.on{background:#00A868;color:#fff}
table{border-collapse:collapse;width:100%;background:#fff;border-radius:12px;overflow:hidden}
td,th{padding:8px 12px;border-bottom:1px #eee solid;font-size:13px;text-align:left}
th{background:#f0f5f2}
.month{margin:18px 0 8px;font-weight:800;color:#0084C6}
.t{background:#fff;border-radius:12px;padding:10px 14px;margin:6px 0;box-shadow:0 2px 8px rgba(0,132,198,.08)}
.badge{font-size:11px;font-weight:800;color:#fff;border-radius:6px;padding:2px 8px;background:#0084C6}
</style></head><body>
<h1>🏸 BWF 数据预览</h1>
<small id="updated"></small>
<div class="tabs" id="tabs"></div><div id="rank"></div><div id="sched"></div>
<script>
const R = __RANKINGS__; const S = __SCHEDULE__;
document.getElementById('updated').textContent = '排名更新于 ' + (R.updatedAt||'') + ' · 赛程更新于 ' + (S.updatedAt||'');
const tabs = document.getElementById('tabs'); const rk = document.getElementById('rank');
let cur = 'ms';
function renderRank(){
  rk.innerHTML = '<table><tr><th>排名</th><th>国家</th><th>选手</th><th>涨跌</th><th>积分</th></tr>' +
    R.disciplines[cur].entries.map(e =>
      `<tr><td>${e.rank}</td><td>${e.country}</td><td>${e.player}</td><td>${e.change||'—'}</td><td>${e.points.toLocaleString()}</td></tr>`).join('') +
    '</table>';
}
Object.keys(R.disciplines).forEach(k => {
  const b = document.createElement('div'); b.className = 'tab'; b.textContent = R.disciplines[k].name;
  b.onclick = () => { cur = k; [...tabs.children].forEach(c => c.classList.remove('on')); b.classList.add('on'); renderRank(); };
  tabs.appendChild(b);
});
tabs.children[0].classList.add('on'); renderRank();
const months = {};
S.tournaments.forEach(t => { const m = t.startDate.slice(0, 7); (months[m] = months[m] || []).push(t); });
document.getElementById('sched').innerHTML = Object.keys(months).sort().map(m =>
  `<div class="month">${parseInt(m.slice(5), 10)}月</div>` + months[m].map(t =>
    `<div class="t"><span class="badge">${t.level}</span> <b>${t.name}</b><br>` +
    `<small>${t.startDate} ~ ${t.endDate} · ${t.city}${t.prizeMoney ? ' · $' + t.prizeMoney.toLocaleString() : ''}</small></div>`).join('')).join('');
</script></body></html>"""


def build_page(rankings: dict, schedule: dict) -> str:
    page = PAGE.replace("__RANKINGS__", json.dumps(rankings, ensure_ascii=False))
    return page.replace("__SCHEDULE__", json.dumps(schedule, ensure_ascii=False))


def main() -> None:
    rankings = json.loads((OUT / "rankings.json").read_text(encoding="utf-8"))
    schedule = json.loads((OUT / "schedule.json").read_text(encoding="utf-8"))
    (OUT / "preview.html").write_text(build_page(rankings, schedule), encoding="utf-8")
    print(f"OK 预览页: {OUT / 'preview.html'}")


if __name__ == "__main__":
    main()
