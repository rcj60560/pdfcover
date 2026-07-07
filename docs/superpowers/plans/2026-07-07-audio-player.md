# 音频播放器 Web 应用实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 pdfcover 项目新建 `audioplayer/` 文件夹，实现一个纯静态音频播放器：卡片网格书库 → 书本音频列表 → 底部常驻播放条，部署到阿里云 nginx，靠 `autoindex json` 自动发现书和音频。

**Architecture:** 纯前端（HTML+CSS+JS，ESM），无后台进程。`core.js` 是无副作用纯逻辑层（解析/排序/循环/倍速/渲染辅助，单测覆盖）；`app.js` 负责 IO/DOM/`<audio>` 接线；nginx 既托管页面又通过 `autoindex_format json` 提供书单与音频清单。本地用 `dev_server.py`（忠实模拟 nginx autoindex json）验证。

**Tech Stack:** 原生 HTML5 / CSS3 / JavaScript (ES Modules)，浏览器原生 `<audio>`，nginx `autoindex`，Node.js 内置测试器（`node --test`，零依赖），Python 标准库（仅本地 dev_server + pytest）。

## Global Constraints

- **纯静态，不引入任何后台进程或新依赖**（pdfcover 的 pyproject.toml 不改）
- **无访问密码**，公开访问
- **一本书 = 一个文件夹**，内部是 MP3 + 规律命名（如 `001.mp3`）
- **PDF 不归本应用**（用户自行在 pad/WPS 打开）
- **中文路径**：拼 URL 时每段必须 `encodeURIComponent`
- **自动发现**：书与音频来自 nginx `autoindex json`，加书 = 传文件夹 + 刷新
- **部署路径**：页面在 `/script/`（autoindex off），音频根在 `/script/books/`（autoindex on, json）
- **不做记忆播放进度**；播放器含：播放/暂停、上下首、±5s、可拖进度条、三档循环、0.75–1.5x 倍速、音量/静音
- 服务器：公网 `47.108.230.162`，SSH 22，Web 80，nginx，用户有 root 可改配置

---

## File Structure

```
pdfcover/
└── audioplayer/
    ├── package.json            # {"type":"module"} + node --test 脚本
    ├── core.js                 # 纯逻辑 + 渲染辅助（ESM，无副作用，单测覆盖）
    ├── app.js                  # IO/DOM/<audio> 接线（ESM，浏览器内运行）
    ├── index.html              # 单页骨架（首页 + 详情 + 播放条）
    ├── style.css               # 响应式卡片网格 + 列表 + 底部播放条
    ├── dev_server.py           # 本地开发服务器，模拟 nginx autoindex json
    ├── nginx.conf.example      # nginx 配置示例
    ├── README.md               # 部署 & 加书 & 本地开发说明
    ├── tests/
    │   ├── core.test.js        # core.js 的 node:test 单测
    │   └── test_dev_server.py  # dev_server.py 的 pytest 单测
    └── fixtures/
        └── books/              # 本地测试假数据
            ├── 剑桥雅思10/{001,002}.mp3
            ├── 新概念2/{001,002}.mp3
            ├── 空书/            # 空目录，测"暂无音频"
            └── readme.txt      # 非目录，测过滤
```

**职责边界：**
- `core.js`：纯函数，输入→输出，无 DOM/网络/`<audio>`。可被 node:test 直接 import。
- `app.js`：所有副作用。import `core.js` 的函数；操作 DOM 与 `audio` 元素；仅浏览器运行。
- `dev_server.py`：`build_autoindex(dirpath)` 是纯函数（可 pytest）；`Handler` 负责本地托管 + 把 `/books/` 映射到 `fixtures/books/`。

---

## Task 1: 脚手架 + dev_server.py（TDD）

**Files:**
- Create: `audioplayer/package.json`
- Create: `audioplayer/dev_server.py`
- Create: `audioplayer/tests/test_dev_server.py`
- Create: `audioplayer/fixtures/books/剑桥雅思10/001.mp3`（空占位）
- Create: `audioplayer/fixtures/books/剑桥雅思10/002.mp3`（空占位）
- Create: `audioplayer/fixtures/books/新概念2/001.mp3`（空占位）
- Create: `audioplayer/fixtures/books/新概念2/002.mp3`（空占位）
- Create: `audioplayer/fixtures/books/空书/.keep`（占位让空目录可提交）
- Create: `audioplayer/fixtures/books/readme.txt`

**Interfaces:**
- Consumes: None
- Produces: `dev_server.build_autoindex(dirpath: str) -> list[dict]`，每项 `{"name":str,"type":"directory"|"file","mtime":"%a, %d %b %Y %H:%M:%S GMT"}`；与 nginx `autoindex_format json` 字段一致。

- [ ] **Step 1: 建目录与占位 fixtures**

```bash
cd "D:/Users/luocj/pyProject/ky/pdfcover"
mkdir -p audioplayer/tests audioplayer/fixtures/books/剑桥雅思10 audioplayer/fixtures/books/新概念2 audioplayer/fixtures/books/空书
touch audioplayer/fixtures/books/剑桥雅思10/001.mp3 audioplayer/fixtures/books/剑桥雅思10/002.mp3
touch audioplayer/fixtures/books/新概念2/001.mp3 audioplayer/fixtures/books/新概念2/002.mp3
touch audioplayer/fixtures/books/空书/.keep
printf 'not a book' > audioplayer/fixtures/books/readme.txt
```

- [ ] **Step 2: 写 package.json**

Create `audioplayer/package.json`:

```json
{
  "name": "pdfcover-audioplayer",
  "private": true,
  "type": "module",
  "scripts": {
    "test": "node --test tests/"
  }
}
```

- [ ] **Step 3: 写失败测试 `audioplayer/tests/test_dev_server.py`**

```python
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dev_server import build_autoindex


def test_build_autoindex_format(tmp_path):
    (tmp_path / "001.mp3").write_bytes(b"")
    (tmp_path / "sub").mkdir()

    result = build_autoindex(str(tmp_path))

    assert isinstance(result, list)
    by_name = {e["name"]: e for e in result}
    assert set(by_name) == {"001.mp3", "sub"}
    assert by_name["001.mp3"]["type"] == "file"
    assert by_name["sub"]["type"] == "directory"
    for e in result:
        assert set(e.keys()) == {"name", "type", "mtime"}
        assert e["mtime"].endswith("GMT")
```

- [ ] **Step 4: 运行测试，确认失败**

```bash
cd "D:/Users/luocj/pyProject/ky/pdfcover"
pytest audioplayer/tests/test_dev_server.py -v
```

Expected: FAIL（`ModuleNotFoundError: No module named 'dev_server'`）

- [ ] **Step 5: 实现 `audioplayer/dev_server.py`**

```python
"""本地开发服务器：托管静态文件，并对目录请求返回与 nginx `autoindex json`
完全相同格式的 JSON，使本地验证与线上一致。

用法：
    python dev_server.py [port]      # 默认 8000

页面文件（index.html/app.js/style.css）从脚本所在目录提供；
/books/** 映射到 fixtures/books/**。
"""

import json
import mimetypes
import os
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import unquote, urlparse

BASE = os.path.dirname(os.path.abspath(__file__))
BOOKS_DIR = os.path.join(BASE, "fixtures", "books")


def _entry(name, full):
    typ = "directory" if os.path.isdir(full) else "file"
    mtime = datetime.fromtimestamp(os.path.getmtime(full), tz=timezone.utc)
    return {
        "name": name,
        "type": typ,
        "mtime": mtime.strftime("%a, %d %b %Y %H:%M:%S GMT"),
    }


def build_autoindex(dirpath):
    """返回与 nginx autoindex_format json 一致结构的列表。纯函数，可单测。"""
    return [
        _entry(n, os.path.join(dirpath, n))
        for n in sorted(os.listdir(dirpath))
    ]


def to_disk(url_path):
    """URL 路径 -> 磁盘路径。/books/** 映射到 fixtures/books/**。"""
    rel = unquote(url_path).lstrip("/")
    if rel == "books" or rel.startswith("books/"):
        sub = rel[len("books/"):] if rel.startswith("books/") else ""
        return os.path.join(BOOKS_DIR, sub)
    return os.path.join(BASE, rel)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        disk = to_disk(path)

        if disk.endswith(os.sep) or path.endswith("/") or os.path.isdir(disk):
            if os.path.isdir(disk):
                self._send_json(build_autoindex(disk))
                return

        if os.path.isfile(disk):
            self._send_file(disk)
            return

        self.send_error(404, "Not Found")

    def _send_json(self, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, disk):
        with open(disk, "rb") as f:
            data = f.read()
        ctype = mimetypes.guess_type(disk)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):  # 静音默认日志，按需注释
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))


def main(port=8000):
    print(f"dev server on http://127.0.0.1:{port}/   (root={BASE})")
    print("books ->", BOOKS_DIR)
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 8000)
```

- [ ] **Step 6: 运行测试，确认通过**

```bash
cd "D:/Users/luocj/pyProject/ky/pdfcover"
pytest audioplayer/tests/test_dev_server.py -v
```

Expected: PASS（1 passed）

- [ ] **Step 7: 提交**

```bash
cd "D:/Users/luocj/pyProject/ky/pdfcover"
git add audioplayer/
git commit -m "feat(audioplayer): scaffold folder, dev_server mimicking nginx autoindex json"
```

---

## Task 2: core.js 纯逻辑与渲染辅助（TDD）

**Files:**
- Create: `audioplayer/core.js`
- Create: `audioplayer/tests/core.test.js`

**Interfaces:**
- Consumes: None
- Produces（后续 app.js 依赖，签名固定）:
  - `parseBooks(entries: object[]) -> string[]`（取 type==="directory" 的 name）
  - `parseTracks(entries: object[]) -> string[]`（取 .mp3 file 的 name，大小写不敏感）
  - `sortTracks(names: string[]) -> string[]`（按前导数字自然排序，返回新数组）
  - `cycleLoop(mode: "off"|"one"|"all") -> "off"|"one"|"all"`（off→one→all→off）
  - `cycleSpeed(speed: number) -> number`（0.75→1→1.25→1.5→0.75；未知值归 1）
  - `nextTrack(index, total, loopMode) -> number|null`（one 重播当前；all 回绕；off 到尾停止返回 null）
  - `clampSeek(time, duration) -> number`（夹到 [0,duration]，duration 非正返回 0）
  - `formatTime(sec) -> string`（"m:ss"）
  - `renderBookCard(name, count) -> string`（HTML 字符串，含 `data-book`）
  - `renderTrackRow(name, index, isCurrent) -> string`（HTML 字符串，含 `data-index`，当前项含 `is-current`）

- [ ] **Step 1: 写失败测试 `audioplayer/tests/core.test.js`**

```javascript
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  parseBooks, parseTracks, sortTracks,
  cycleLoop, cycleSpeed, nextTrack, clampSeek,
  formatTime, renderBookCard, renderTrackRow,
} from "../core.js";

test("parseBooks keeps directories only", () => {
  const entries = [
    { name: "book1", type: "directory" },
    { name: "readme.txt", type: "file" },
    { name: "book2", type: "directory" },
  ];
  assert.deepEqual(parseBooks(entries), ["book1", "book2"]);
});

test("parseBooks tolerates non-array", () => {
  assert.deepEqual(parseBooks(null), []);
  assert.deepEqual(parseBooks(undefined), []);
});

test("parseTracks keeps mp3 files only (case-insensitive)", () => {
  const entries = [
    { name: "001.mp3", type: "file" },
    { name: "001.txt", type: "file" },
    { name: "sub", type: "directory" },
    { name: "002.MP3", type: "file" },
  ];
  assert.deepEqual(parseTracks(entries), ["001.mp3", "002.MP3"]);
});

test("sortTracks numeric order for unpadded", () => {
  assert.deepEqual(sortTracks(["10.mp3", "2.mp3", "1.mp3"]), ["1.mp3", "2.mp3", "10.mp3"]);
});

test("sortTracks zero-padded order", () => {
  assert.deepEqual(sortTracks(["020.mp3", "001.mp3", "002.mp3"]), ["001.mp3", "002.mp3", "020.mp3"]);
});

test("sortTracks does not mutate input", () => {
  const input = ["2.mp3", "1.mp3"];
  sortTracks(input);
  assert.deepEqual(input, ["2.mp3", "1.mp3"]);
});

test("cycleLoop off->one->all->off", () => {
  assert.equal(cycleLoop("off"), "one");
  assert.equal(cycleLoop("one"), "all");
  assert.equal(cycleLoop("all"), "off");
});

test("cycleSpeed cycles and resets unknown", () => {
  assert.equal(cycleSpeed(1), 1.25);
  assert.equal(cycleSpeed(1.25), 1.5);
  assert.equal(cycleSpeed(1.5), 0.75);
  assert.equal(cycleSpeed(0.75), 1);
  assert.equal(cycleSpeed(999), 1);
});

test("nextTrack off stops at end", () => {
  assert.equal(nextTrack(0, 3, "off"), 1);
  assert.equal(nextTrack(2, 3, "off"), null);
});

test("nextTrack one repeats current", () => {
  assert.equal(nextTrack(2, 3, "one"), 2);
});

test("nextTrack all wraps to 0", () => {
  assert.equal(nextTrack(2, 3, "all"), 0);
});

test("clampSeek clamps to [0,duration]", () => {
  assert.equal(clampSeek(-5, 100), 0);
  assert.equal(clampSeek(200, 100), 100);
  assert.equal(clampSeek(50, 100), 50);
  assert.equal(clampSeek(50, 0), 0);
  assert.equal(clampSeek(50, NaN), 0);
});

test("formatTime m:ss", () => {
  assert.equal(formatTime(0), "0:00");
  assert.equal(formatTime(65), "1:05");
  assert.equal(formatTime(NaN), "0:00");
});

test("renderBookCard embeds name and count", () => {
  const html = renderBookCard("剑桥10", 20);
  assert.match(html, /data-book="剑桥10"/);
  assert.match(html, /剑桥10/);
  assert.match(html, /20集/);
});

test("renderBookCard omits count when not a number", () => {
  const html = renderBookCard("书", NaN);
  assert.doesNotMatch(html, /集/);
});

test("renderTrackRow marks current only when asked", () => {
  assert.doesNotMatch(renderTrackRow("001.mp3", 0, false), /is-current/);
  assert.match(renderTrackRow("002.mp3", 1, true), /is-current/);
  assert.match(renderTrackRow("002.mp3", 1, true), /data-index="1"/);
});

test("renderBookCard escapes special chars", () => {
  const html = renderBookCard('a"<b>', 1);
  assert.doesNotMatch(html, /data-book="a"<b>"/); // 引号被转义，不破坏属性
  assert.match(html, /&quot;/);
});
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd "D:/Users/luocj/pyProject/ky/pdfcover/audioplayer"
node --test tests/
```

Expected: FAIL（`Cannot find module '.../core.js'`）

- [ ] **Step 3: 实现 `audioplayer/core.js`**

```javascript
// audioplayer/core.js
// 纯逻辑 + 渲染辅助，无副作用（无 DOM / 网络 / <audio>），可在 node:test 中单测。

export const LOOP_MODES = ["off", "one", "all"];
export const SPEEDS = [0.75, 1, 1.25, 1.5];
const CARD_COLORS = [
  "#e57373", "#f06292", "#ba68c8", "#7986cb", "#4fc3f7",
  "#4db6ac", "#81c784", "#ffb74d", "#a1887f", "#90a4ae",
];

export function parseBooks(entries) {
  if (!Array.isArray(entries)) return [];
  return entries.filter((e) => e && e.type === "directory").map((e) => e.name);
}

export function parseTracks(entries) {
  if (!Array.isArray(entries)) return [];
  return entries
    .filter((e) => e && e.type === "file" && /\.mp3$/i.test(e.name))
    .map((e) => e.name);
}

export function sortTracks(names) {
  return [...names].sort((a, b) => {
    const na = parseInt(a, 10);
    const nb = parseInt(b, 10);
    if (!isNaN(na) && !isNaN(nb)) {
      if (na !== nb) return na - nb;
      return a.localeCompare(b);
    }
    if (!isNaN(na)) return -1;
    if (!isNaN(nb)) return 1;
    return a.localeCompare(b);
  });
}

export function cycleLoop(mode) {
  const i = LOOP_MODES.indexOf(mode);
  return LOOP_MODES[(i + 1) % LOOP_MODES.length];
}

export function cycleSpeed(speed) {
  const i = SPEEDS.indexOf(speed);
  return i === -1 ? 1 : SPEEDS[(i + 1) % SPEEDS.length];
}

export function nextTrack(index, total, loopMode) {
  if (loopMode === "one") return index;
  if (index < total - 1) return index + 1;
  if (loopMode === "all") return 0;
  return null;
}

export function clampSeek(time, duration) {
  if (!Number.isFinite(duration) || duration <= 0) return 0;
  return Math.max(0, Math.min(time, duration));
}

export function formatTime(sec) {
  if (!Number.isFinite(sec) || sec < 0) sec = 0;
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

function esc(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function colorFor(name) {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0;
  return CARD_COLORS[h % CARD_COLORS.length];
}

export function renderBookCard(name, count) {
  const first = [...String(name)][0] || "?";
  const color = colorFor(String(name));
  const countLabel = Number.isFinite(count) ? `${count}集` : "";
  return (
    `<button class="card" data-book="${esc(name)}" style="--card-color:${color}">` +
    `<span class="card-cover" style="background:${color}">${esc(first)}</span>` +
    `<span class="card-title">${esc(name)}</span>` +
    `<span class="card-count">${countLabel}</span>` +
    `</button>`
  );
}

export function renderTrackRow(name, index, isCurrent) {
  const num = parseInt(name, 10);
  const label = Number.isFinite(num) ? String(num).padStart(3, "0") : esc(name);
  return (
    `<li class="track${isCurrent ? " is-current" : ""}" data-file="${esc(name)}" data-index="${index}">` +
    `<span class="track-num">${esc(label)}</span>` +
    `<span class="track-name">${esc(name)}</span>` +
    `<span class="track-dur"></span>` +
    `<span class="track-ind"></span>` +
    `</li>`
  );
}
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
cd "D:/Users/luocj/pyProject/ky/pdfcover/audioplayer"
node --test tests/
```

Expected: PASS（所有 core 测试通过；dev_server 的 pytest 不在此命令范围）

- [ ] **Step 5: 提交**

```bash
cd "D:/Users/luocj/pyProject/ky/pdfcover"
git add audioplayer/core.js audioplayer/tests/core.test.js
git commit -m "feat(audioplayer): add pure core logic (parse/sort/loop/speed/render) with tests"
```

---

## Task 3: index.html + style.css（UI 骨架）

**Files:**
- Create: `audioplayer/index.html`
- Create: `audioplayer/style.css`

**Interfaces:**
- Consumes: `app.js`（下一任务创建，`<script type="module" src="app.js">`）
- Produces: 固定的 DOM id 供 app.js 操作：`back-btn`、`view-title`、`home-view`、`book-grid`、`home-msg`、`detail-view`、`track-list`、`detail-msg`、`player`、`now-title`、`cur-time`、`seek`、`dur-time`、`prev`、`back5`、`play`、`fwd5`、`next`、`loop`、`speed`、`mute`、`audio`。class：`card`（含 `data-book`）、`track`（含 `data-index`，可选 `is-current`/`is-broken`）。

- [ ] **Step 1: 写 `audioplayer/index.html`**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
  <title>我的书库</title>
  <link rel="stylesheet" href="style.css" />
</head>
<body>
  <header class="topbar">
    <button id="back-btn" class="back" type="button" hidden>← 返回</button>
    <h1 id="view-title">📚 我的书库</h1>
  </header>

  <main>
    <section id="home-view">
      <div id="book-grid" class="grid"></div>
      <p id="home-msg" class="msg" hidden></p>
    </section>

    <section id="detail-view" hidden>
      <ul id="track-list" class="tracks"></ul>
      <p id="detail-msg" class="msg" hidden></p>
    </section>
  </main>

  <footer id="player" class="player" hidden>
    <div class="player-info"><span id="now-title">—</span></div>
    <div class="player-progress">
      <span id="cur-time" class="t">0:00</span>
      <input id="seek" type="range" min="0" max="1000" value="0" />
      <span id="dur-time" class="t">0:00</span>
    </div>
    <div class="player-controls">
      <button id="prev" type="button" title="上一首">⏮</button>
      <button id="back5" type="button" title="后退5秒">«5s</button>
      <button id="play" type="button" title="播放/暂停">▶</button>
      <button id="fwd5" type="button" title="快进5秒">5s»</button>
      <button id="next" type="button" title="下一首">⏭</button>
      <button id="loop" type="button" title="循环">🔁</button>
      <button id="speed" type="button" title="倍速">1x</button>
      <button id="mute" type="button" title="静音">🔊</button>
    </div>
  </footer>

  <audio id="audio" preload="metadata"></audio>
  <script type="module" src="app.js"></script>
</body>
</html>
```

- [ ] **Step 2: 写 `audioplayer/style.css`**

```css
:root { --accent: #3b82f6; }
* { box-sizing: border-box; }
html, body { height: 100%; }
body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
  background: #f5f5f7;
  color: #1d1d1f;
  padding-bottom: 150px; /* 给底部播放条留位 */
}
.topbar {
  position: sticky; top: 0; z-index: 5;
  background: rgba(255,255,255,.92); backdrop-filter: saturate(180%) blur(10px);
  border-bottom: 1px solid #e5e5ea;
  padding: 12px 16px; display: flex; align-items: center; gap: 12px;
}
.topbar h1 { font-size: 18px; margin: 0; flex: 1; }
.back { border: none; background: transparent; font-size: 15px; color: var(--accent); cursor: pointer; padding: 6px 8px; }
main { max-width: 1100px; margin: 0 auto; padding: 16px; }

/* 卡片网格 */
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 14px; }
.card {
  display: flex; flex-direction: column; align-items: center; gap: 8px;
  padding: 16px 10px; background: #fff; border: 1px solid #eee; border-radius: 14px;
  cursor: pointer; transition: transform .08s, box-shadow .2s; text-align: center;
}
.card:hover { box-shadow: 0 4px 14px rgba(0,0,0,.08); }
.card:active { transform: scale(.98); }
.card-cover {
  width: 64px; height: 64px; border-radius: 14px; display: flex; align-items: center; justify-content: center;
  color: #fff; font-size: 30px; font-weight: 600;
}
.card-title { font-size: 13px; line-height: 1.3; word-break: break-word; }
.card-count { font-size: 11px; color: #86868b; }

/* 音频列表 */
.tracks { list-style: none; margin: 0; padding: 0; }
.track {
  display: flex; align-items: center; gap: 12px; padding: 14px 8px;
  border-bottom: 1px solid #f0f0f0; cursor: pointer;
}
.track:hover { background: #fafafa; }
.track-num { width: 40px; font-variant-numeric: tabular-nums; color: #86868b; }
.track-name { flex: 1; font-size: 14px; word-break: break-all; }
.track-dur { color: #86868b; font-size: 12px; min-width: 40px; text-align: right; }
.track-ind { width: 16px; color: var(--accent); }
.track.is-current { color: var(--accent); }
.track.is-current .track-num { color: var(--accent); }
.track.is-current .track-ind::after { content: "▶"; }
.track.is-broken { color: #d32f2f; text-decoration: line-through; }

.msg { text-align: center; color: #86868b; padding: 40px 0; }

/* 底部播放条 */
.player {
  position: fixed; bottom: 0; left: 0; right: 0; z-index: 10;
  background: rgba(255,255,255,.96); backdrop-filter: blur(10px);
  border-top: 1px solid #e5e5ea; padding: 8px 12px;
  display: flex; flex-direction: column; gap: 6px;
  max-width: 1100px; margin: 0 auto;
}
.player-info { text-align: center; font-size: 13px; min-height: 18px; }
.player-progress { display: flex; align-items: center; gap: 8px; }
.player-progress .t { font-size: 12px; color: #86868b; min-width: 34px; }
.player-progress input[type="range"] { flex: 1; }
.player-controls { display: flex; justify-content: center; flex-wrap: wrap; gap: 6px; }
.player-controls button {
  border: 1px solid #e5e5ea; background: #fff; border-radius: 10px;
  padding: 8px 12px; font-size: 15px; cursor: pointer; min-width: 44px;
}
.player-controls button:hover { background: #f5f5f7; }
.player-controls button.active { background: var(--accent); color: #fff; border-color: var(--accent); }

@media (max-width: 600px) {
  .grid { grid-template-columns: repeat(auto-fill, minmax(110px, 1fr)); gap: 10px; }
  .card-cover { width: 52px; height: 52px; font-size: 24px; }
}
```

- [ ] **Step 3: 手动验证（此时 app.js 还不存在，页面会报 404，正常）**

```bash
cd "D:/Users/luocj/pyProject/ky/pdfcover/audioplayer"
python dev_server.py 8000
```

浏览器打开 `http://127.0.0.1:8000/`，应看到顶部栏「📚 我的书库」、空白主区、（播放条 hidden）。控制台会有 `app.js 404`，属正常（下一任务补上）。确认无样式错乱后 `Ctrl+C` 停服。

- [ ] **Step 4: 提交**

```bash
cd "D:/Users/luocj/pyProject/ky/pdfcover"
git add audioplayer/index.html audioplayer/style.css
git commit -m "feat(audioplayer): add index.html shell and responsive styles"
```

---

## Task 4: app.js —— 数据加载 + 渲染 + 导航

**Files:**
- Create: `audioplayer/app.js`

**Interfaces:**
- Consumes（来自 core.js）：`parseBooks`、`parseTracks`、`sortTracks`、`renderBookCard`、`renderTrackRow`
- Produces：全局 `state`（`{books, currentBook, currentIndex, loop:'off', speed:1}`），DOM 事件绑定。本任务实现到"卡片渲染 + 点书进详情 + 列表渲染"。播放逻辑在 Task 5。

- [ ] **Step 1: 写 `audioplayer/app.js`（加载/渲染/导航部分，播放控件先占位）**

```javascript
// audioplayer/app.js
import {
  parseBooks, parseTracks, sortTracks,
  renderBookCard, renderTrackRow,
} from "./core.js";

const BOOKS = "books/"; // 相对页面：prod 解析为 /script/books/，本地为 /books/
const $ = (id) => document.getElementById(id);
const audio = $("audio");

const state = {
  books: [],          // [{ name, tracks: [filename,...] }]
  currentBook: null,  // 当前书名
  currentIndex: -1,   // 当前曲目下标
  loop: "off",
  speed: 1,
};

function currentBook() {
  return state.books.find((b) => b.name === state.currentBook);
}

async function fetchJson(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error("HTTP " + res.status);
  return res.json();
}

/* ---------- 视图切换 ---------- */
function showHome() {
  $("detail-view").hidden = true;
  $("home-view").hidden = false;
  $("back-btn").hidden = true;
  $("view-title").textContent = "📚 我的书库";
}
function showDetail(name) {
  $("home-view").hidden = true;
  $("detail-view").hidden = false;
  $("back-btn").hidden = false;
  $("view-title").textContent = name;
}

/* ---------- 首页 ---------- */
async function loadHome() {
  const msg = $("home-msg");
  msg.hidden = true;
  try {
    const names = parseBooks(await fetchJson(BOOKS));
    const books = [];
    for (const name of names) {
      try {
        const tracks = sortTracks(parseTracks(await fetchJson(BOOKS + encodeURIComponent(name) + "/")));
        if (tracks.length) books.push({ name, tracks });
      } catch (_) {
        /* 单本拉取失败不影响整体 */
      }
    }
    state.books = books;
    $("book-grid").innerHTML = books.map((b) => renderBookCard(b.name, b.tracks.length)).join("");
    if (!books.length) {
      msg.textContent = "暂无书目";
      msg.hidden = false;
    }
  } catch (e) {
    msg.textContent = "加载失败，请检查服务或 nginx 配置";
    msg.hidden = false;
  }
}

/* ---------- 详情 ---------- */
async function openBook(name) {
  if (!state.books.find((b) => b.name === name)) {
    try {
      const tracks = sortTracks(parseTracks(await fetchJson(BOOKS + encodeURIComponent(name) + "/")));
      if (tracks.length) state.books.push({ name, tracks });
    } catch (_) {
      /* ignore */
    }
  }
  state.currentBook = name;
  state.currentIndex = -1;
  showDetail(name);
  renderTracks();
  const b = currentBook();
  const m = $("detail-msg");
  m.hidden = true;
  if (!b || !b.tracks.length) {
    m.textContent = "暂无音频";
    m.hidden = false;
  }
}

function renderTracks() {
  const b = currentBook();
  const tracks = b ? b.tracks : [];
  $("track-list").innerHTML = tracks
    .map((f, i) => renderTrackRow(f, i, i === state.currentIndex))
    .join("");
}

/* ---------- 事件（播放相关在 Task 5 接入；本任务先绑导航与选曲占位）---------- */
function bind() {
  $("back-btn").addEventListener("click", showHome);

  $("book-grid").addEventListener("click", (e) => {
    const card = e.target.closest(".card");
    if (!card) return;
    openBook(card.dataset.book);
  });

  $("track-list").addEventListener("click", (e) => {
    const row = e.target.closest(".track");
    if (!row) return;
    // 播放逻辑在 Task 5；这里先标记选中行，便于本任务验证
    state.currentIndex = Number(row.dataset.index);
    renderTracks();
  });
}

bind();
showHome();
loadHome();
```

- [ ] **Step 2: 手动验证：首页卡片 + 进详情 + 列表**

```bash
cd "D:/Users/luocj/pyProject/ky/pdfcover/audioplayer"
python dev_server.py 8000
```

浏览器 `http://127.0.0.1:8000/`，预期：
- 首页出现 2 张卡片（剑桥雅思10、新概念2），各显示「2集」；`空书` 与 `readme.txt` 不出现。
- 点「剑桥雅思10」→ 进入详情，标题变书名，列出 `001`、`002` 两行；顶部「← 返回」可回首页。
- 点某行 → 该行变高亮（is-current）。
- 播放条仍隐藏、点行不发声（播放逻辑下一任务）。`Ctrl+C` 停服。

- [ ] **Step 3: 提交**

```bash
cd "D:/Users/luocj/pyProject/ky/pdfcover"
git add audioplayer/app.js
git commit -m "feat(audioplayer): load books/tracks via autoindex, render cards and track list"
```

---

## Task 5: app.js —— 播放与控件

**Files:**
- Modify: `audioplayer/app.js`（在 Task 4 基础上接入播放）

**Interfaces:**
- Consumes（新增来自 core.js）：`cycleLoop`、`cycleSpeed`、`nextTrack`、`clampSeek`、`formatTime`
- Produces：完整可用的播放器。

- [ ] **Step 1: 修改 `app.js` 的 import 行，加入播放用函数**

把第 2–5 行的 import 改为：

```javascript
import {
  parseBooks, parseTracks, sortTracks,
  cycleLoop, cycleSpeed, nextTrack, clampSeek, formatTime,
  renderBookCard, renderTrackRow,
} from "./core.js";
```

- [ ] **Step 2: 在 `renderTracks()` 函数之后、`bind()` 之前，插入播放相关函数**

```javascript
/* ---------- 播放 ---------- */
function trackUrl(book, file) {
  return BOOKS + encodeURIComponent(book) + "/" + encodeURIComponent(file);
}

function playIndex(i) {
  const b = currentBook();
  if (!b || i < 0 || i >= b.tracks.length) return;
  state.currentIndex = i;
  audio.src = trackUrl(b.name, b.tracks[i]);
  audio.playbackRate = state.speed;
  audio.load();
  audio.play().catch(() => {}); // 加载失败的兜底在 'error' 事件处理（Task 6）
  $("player").hidden = false;
  updateNowPlaying();
  renderTracks();
}

function updateNowPlaying() {
  const b = currentBook();
  if (!b || state.currentIndex < 0) return;
  $("now-title").textContent = b.tracks[state.currentIndex] + " · " + b.name;
}

function togglePlay() {
  const b = currentBook();
  if (!audio.src) {
    if (b && b.tracks.length) playIndex(state.currentIndex < 0 ? 0 : state.currentIndex);
    return;
  }
  if (audio.paused) audio.play().catch(() => {});
  else audio.pause();
}

function gotoNext() {
  const b = currentBook();
  if (!b) return;
  const n = nextTrack(state.currentIndex, b.tracks.length, state.loop);
  if (n === null) {
    audio.pause();
    return;
  }
  playIndex(n);
}

function updateLoopButton() {
  const btn = $("loop");
  btn.textContent = state.loop === "one" ? "🔂" : "🔁";
  btn.classList.toggle("active", state.loop !== "off");
  btn.title = "循环：" + (state.loop === "off" ? "关" : state.loop === "one" ? "单曲" : "整本");
}
```

- [ ] **Step 3: 替换 `bind()` 函数，接入全部控件**

```javascript
function bind() {
  $("back-btn").addEventListener("click", showHome);

  $("book-grid").addEventListener("click", (e) => {
    const card = e.target.closest(".card");
    if (!card) return;
    openBook(card.dataset.book);
  });

  $("track-list").addEventListener("click", (e) => {
    const row = e.target.closest(".track");
    if (!row) return;
    playIndex(Number(row.dataset.index));
  });

  $("play").addEventListener("click", togglePlay);

  $("prev").addEventListener("click", () => {
    playIndex(Math.max(0, state.currentIndex - 1));
  });
  $("next").addEventListener("click", gotoNext);

  $("back5").addEventListener("click", () => {
    audio.currentTime = clampSeek(audio.currentTime - 5, audio.duration);
  });
  $("fwd5").addEventListener("click", () => {
    audio.currentTime = clampSeek(audio.currentTime + 5, audio.duration);
  });

  $("loop").addEventListener("click", () => {
    state.loop = cycleLoop(state.loop);
    updateLoopButton();
  });

  $("speed").addEventListener("click", () => {
    state.speed = cycleSpeed(state.speed);
    audio.playbackRate = state.speed;
    $("speed").textContent = state.speed + "x";
  });

  $("mute").addEventListener("click", () => {
    audio.muted = !audio.muted;
    $("mute").textContent = audio.muted ? "🔇" : "🔊";
  });

  $("seek").addEventListener("input", () => {
    if (audio.duration) audio.currentTime = ($("seek").value / 1000) * audio.duration;
  });

  audio.addEventListener("timeupdate", () => {
    $("cur-time").textContent = formatTime(audio.currentTime);
    if (audio.duration) $("seek").value = (audio.currentTime / audio.duration) * 1000;
  });
  audio.addEventListener("loadedmetadata", () => {
    $("dur-time").textContent = formatTime(audio.duration);
  });
  audio.addEventListener("play", () => ($("play").textContent = "⏸"));
  audio.addEventListener("pause", () => ($("play").textContent = "▶"));
  audio.addEventListener("ended", gotoNext);
  // 'error' 兜底在 Task 6 接入
}
```

- [ ] **Step 4: 手动验证播放与控件**

为能听到声音，先把两个真实小 mp3 放进某本书目录（替换占位空文件），例如：

```bash
# 用你本地的任意 mp3 拷两个进来测试（可选；不放则只能验证控件状态机）
# cp /path/to/real.mp3 audioplayer/fixtures/books/剑桥雅思10/001.mp3
```

```bash
cd "D:/Users/luocj/pyProject/ky/pdfcover/audioplayer"
python dev_server.py 8000
```

浏览器 `http://127.0.0.1:8000/`，预期：
- 进书 → 点 `001` → 播放条出现，`▶` 变 `⏸`，进度/时间走动（若有真实 mp3 则出声；空文件则触发 error，由 Task 6 兜底）。
- `⏮/⏭` 切换曲目并高亮；`«5s/5s»` 跳转（时间条变化）；进度条可拖。
- `🔁` 点三下循环 off→one→all→off，按钮高亮/文案变化；`1x` 点动循环 0.75/1/1.25/1.5；`🔊` 静音切换。
- `← 返回` 回首页，播放不中断。`Ctrl+C` 停服。

- [ ] **Step 5: 提交**

```bash
cd "D:/Users/luocj/pyProject/ky/pdfcover"
git add audioplayer/app.js
git commit -m "feat(audioplayer): wire audio playback, transport, loop, speed, volume controls"
```

---

## Task 6: app.js —— 错误兜底（坏音频标红自动跳、加载失败提示）

**Files:**
- Modify: `audioplayer/app.js`

**Interfaces:**
- Consumes: `state`、`gotoNext`、`renderTracks`（已有）
- Produces：`audio` 的 `error` 事件处理（标红当前行 + 自动下一首）。首页/详情加载失败提示已在 Task 4 内置。

- [ ] **Step 1: 在 `bind()` 内、`audio.addEventListener("ended", gotoNext);` 之后，插入 error 处理**

将该行替换为两行：

```javascript
  audio.addEventListener("ended", gotoNext);
  audio.addEventListener("error", () => {
    const row = document.querySelector(`.track[data-index="${state.currentIndex}"]`);
    if (row) row.classList.add("is-broken");
    gotoNext(); // 自动跳下一首；多首连续损坏会逐个标红直到停止/正常
  });
```

- [ ] **Step 2: 手动验证错误路径**

```bash
cd "D:/Users/luocj/pyProject/ky/pdfcover/audioplayer"
python dev_server.py 8000
```

浏览器 `http://127.0.0.1:8000/`：
- 占位 `.mp3` 是空文件 → 点 `001` 会触发 error：该行变红（删除线），并自动尝试 `002`（也红）。
- 验证加载失败提示：临时停掉 dev_server（`Ctrl+C`）后刷新页面 → 首页显示「加载失败，请检查服务或 nginx 配置」而非白屏。重启服务再刷新恢复。
- 验证空书：访问不存在的书不会被列为卡片（`空书` 无 mp3 已在首页过滤；如手动构造空书详情会显示「暂无音频」）。`Ctrl+C` 停服。

- [ ] **Step 3: 提交**

```bash
cd "D:/Users/luocj/pyProject/ky/pdfcover"
git add audioplayer/app.js
git commit -m "feat(audioplayer): handle broken audio (mark red, auto-skip) and load failures"
```

---

## Task 7: nginx 配置示例 + README

**Files:**
- Create: `audioplayer/nginx.conf.example`
- Create: `audioplayer/README.md`

**Interfaces:**
- Consumes: 前述全部产物
- Produces: 部署与加书文档。

- [ ] **Step 1: 写 `audioplayer/nginx.conf.example`**

```nginx
# ===== 音频播放器 nginx 配置示例 =====
# 放进现有 server { } 块内。
# nginx 的 location 按最长前缀匹配，本配置会覆盖当前把 /script 转发到后端的规则。
# 把 /path/to/script-root/ 改成你服务器上存放 index.html 与 books/ 的实际目录。

# 播放器页面与静态资源（不开列目录）
location /script/ {
    alias /path/to/script-root/;
    autoindex off;
}

# 书库：开启 JSON 目录列表，播放器靠它自动发现书与音频
location /script/books/ {
    alias /path/to/script-root/books/;
    autoindex on;
    autoindex_format json;
}

# 改完测试并重载：
#   nginx -t && nginx -s reload
```

- [ ] **Step 2: 写 `audioplayer/README.md`**

````markdown
# 音频播放器（audioplayer）

纯静态网页音频播放器：卡片网格书库 → 书本音频列表 → 底部常驻播放条。
靠 nginx `autoindex json` 自动发现书与音频，无后台进程。

## 本地开发

```bash
cd audioplayer
python dev_server.py 8000        # 浏览器打开 http://127.0.0.1:8000/
```

`dev_server.py` 把 `/books/` 映射到 `fixtures/books/`，并返回与 nginx 一致格式的目录 JSON。
要听到声音，把真实 mp3 放进 `fixtures/books/<某书>/` 替换占位空文件。

## 单元测试

```bash
cd audioplayer && node --test tests/                 # core.js 纯逻辑
pytest audioplayer/tests/test_dev_server.py -v       # dev_server autoindex 格式
```

## 目录结构

- `index.html / app.js / style.css` —— 上线要传的 3 个文件
- `core.js` —— 纯逻辑（解析/排序/循环/倍速/渲染），单测覆盖
- `books/` —— 音频根目录（上线后由你创建并放书）
- `fixtures/` —— 本地测试假数据（不上线）
- `dev_server.py` —— 本地开发服务器（不上线）
- `nginx.conf.example` —— nginx 配置示例

## 部署到服务器（公网 47.108.230.162）

1. **上传 3 个前端文件**到 nginx 静态根下的某个目录（设为 `<script根>`）：

   ```bash
   scp index.html app.js style.css root@47.108.230.162:<script根>/
   ```

2. **创建音频根目录并放书**：

   ```bash
   ssh root@47.108.230.162 'mkdir -p <script根>/books'
   scp -r 剑桥雅思10 root@47.108.230.162:<script根>/books/
   ```

   每本书一个文件夹，里面是 `001.mp3`、`002.mp3`… 命名规律即可。

3. **配 nginx**：把 `nginx.conf.example` 里的 `/path/to/script-root/` 改成 `<script根>` 的实际路径，加进现有 `server { }` 块，然后：

   ```bash
   ssh root@47.108.230.162 'nginx -t && nginx -s reload'
   ```

4. **访问** `http://47.108.230.162/script/`。

## 加一本书

```bash
scp -r 新书名 root@47.108.230.162:<script根>/books/
```

刷新网页，新卡片自动出现。无需任何命令或脚本。
````

- [ ] **Step 3: 提交**

```bash
cd "D:/Users/luocj/pyProject/ky/pdfcover"
git add audioplayer/nginx.conf.example audioplayer/README.md
git commit -m "docs(audioplayer): add nginx config example and deploy/usage README"
```

---

## Task 8: 端到端本地验证 + 全量测试

**Files:**
- Possibly modify: `audioplayer/app.js` / `core.js`（如验证中发现问题）

**Interfaces:**
- Consumes: 全部前序产物
- Produces: 通过验证的可用应用。

- [ ] **Step 1: 跑全部单测**

```bash
cd "D:/Users/luocj/pyProject/ky/pdfcover/audioplayer"
node --test tests/
cd ..
pytest audioplayer/tests/test_dev_server.py -v
```

Expected：全部 PASS。

- [ ] **Step 2: 放入真实 mp3 做端到端走查**

```bash
# 拷 2 个真实 mp3 进剑桥雅思10（覆盖占位空文件）
cp "<你的某个mp3>" "D:/Users/luocj/pyProject/ky/pdfcover/audioplayer/fixtures/books/剑桥雅思10/001.mp3"
cp "<你的某个mp3>" "D:/Users/luocj/pyProject/ky/pdfcover/audioplayer/fixtures/books/剑桥雅思10/002.mp3"
cd "D:/Users/luocj/pyProject/ky/pdfcover/audioplayer"
python dev_server.py 8000
```

浏览器 `http://127.0.0.1:8000/`，按清单走查：
- [ ] 首页 2 张卡片（剑桥雅思10、新概念2），各显示「2集」
- [ ] 点剑桥雅思10 → 列出 001、002，点 001 出声、行高亮
- [ ] `⏸` 暂停/`▶` 继续；`⏭` 到 002；`⏮` 回 001
- [ ] `«5s`/`5s»` 跳转；进度条可拖；时间显示正确
- [ ] `🔁` 切 off/one/all（one 时单首循环；all 时到尾回 001）
- [ ] `1x` 切 0.75/1/1.25/1.5（播放变速可听出）
- [ ] `🔊` 静音/恢复
- [ ] `← 返回` 回首页，播放不中断
- [ ] 用浏览器开发者工具切到手机视图：卡片变 2 列、播放条不挡内容

发现问题就改 `app.js`/`core.js`，回归 Step 1 测试。

- [ ] **Step 3: 还原占位 fixtures（不要把大 mp3 提交进去）**

```bash
cd "D:/Users/luocj/pyProject/ky/pdfcover/audioplayer"
: > fixtures/books/剑桥雅思10/001.mp3
: > fixtures/books/剑桥雅思10/002.mp3
git status   # 确认 fixtures 下无大文件改动；若有真实 mp3 残留用 git checkout 还原
```

- [ ] **Step 4: 提交（若有修复）**

```bash
cd "D:/Users/luocj/pyProject/ky/pdfcover"
git add -A audioplayer/
git commit -m "test(audioplayer): end-to-end local verification pass" || echo "无改动，跳过提交"
```

---

## Task 9: 部署到服务器并真机验证

**Files:** 无代码改动（操作型任务）

**说明：** 此任务在服务器上操作，需要用户提供 `<script根>` 的实际路径（即用户现在上传图片能访问的那个目录体系的对应位置）。先与用户确认该路径再执行。

- [ ] **Step 1: 与用户确认服务器上的目标目录路径**（即 nginx 静态根下放 `script` 内容的位置）

- [ ] **Step 2: 上传前端 3 文件**

```bash
scp "D:/Users/luocj/pyProject/ky/pdfcover/audioplayer/index.html" \
    "D:/Users/luocj/pyProject/ky/pdfcover/audioplayer/app.js" \
    "D:/Users/luocj/pyProject/ky/pdfcover/audioplayer/style.css" \
    root@47.108.230.162:<script根>/
```

- [ ] **Step 3: 创建 books 目录并上传第一本书**

```bash
ssh root@47.108.230.162 "mkdir -p <script根>/books"
scp -r "<本地某书文件夹>" root@47.108.230.162:<script根>/books/
```

- [ ] **Step 4: 配置 nginx（把示例里路径替换为真实值后写入 server 块）**

```bash
# 在服务器上编辑 nginx 配置，加入 Task 7 的两个 location 块（路径替换为 <script根>）
ssh root@47.108.230.162 "nginx -t && nginx -s reload"
```

- [ ] **Step 5: 真机验证**

- 手机/pad 浏览器打开 `http://47.108.230.162/script/`
- [ ] 首页出现该书卡片
- [ ] 进书、点音频可播放
- [ ] 控件（上下首/±5s/循环/倍速/音量）正常
- [ ] 在 pad 上同时用 WPS/其他 app 打开对应 PDF 对照，确认流程顺畅

- [ ] **Step 6: 记录最终结果**（如需，更新 README 补充真实路径或备注）

---

## Self-Review 备注

- **Spec 覆盖**：架构(§2)→T1/T3/T4；autoindex 发现(§2.1)→T1 dev_server + T4 加载；卡片网格(§3.1)→T3 样式+T4 渲染；音频列表(§3.2)→T3+T4；播放条与控件(§3.3,§4)→T3+T5；倍速/三档循环/不记忆进度(§4)→T5+core；中文编码(§7.1)→core esc + app.js encodeURIComponent；排序(§7.2)→core.sortTracks；纯逻辑抽离(§7.3)→core.js；错误处理(§8)→T4(加载)+T6(坏音频)；测试(§9)→T1/T2 单测+T8 E2E；部署(§6)→T7 文档+T9 操作。
- **类型一致**：`state.loop` 取值 `off/one/all` 与 `cycleLoop`/`nextTrack` 一致；`state.speed` 与 `SPEEDS` 一致；DOM id 与各任务引用一致。
- **无占位符**：所有代码步骤含完整代码；运行命令含预期输出。
