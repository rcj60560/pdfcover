# 字幕跟读器（subtitle-viewer）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 外部播放视频/音频时，手机浏览器打开部署在 47 公网的纯静态页，手动对时后字幕 MD 自动滚动跟读。

**Architecture:** 纯静态前端（列表 → 字幕视图，core.js 纯逻辑 + app.js 副作用）+ `sync_subtitles.py` 把本地 MD 与前端 scp 到服务器；本地 `dev_server.py` 预览（`/docs/**` 映射本地目录、`/manifest.json` 动态生成，与线上格式一致）。无后端。

**Tech Stack:** 原生 JS（ES modules，零依赖，`node --test` 单测）；Python 3.10+ 标准库（`http.server`、pytest）；ssh/scp 部署（同 speaking-player 模式）。

**Spec:** `docs/superpowers/specs/2026-09-11-subtitle-viewer-design.md`

## Global Constraints

- 前端零依赖：不用 npm 包、不用构建步骤，`node --test` 直接跑
- 时间戳格式：`` `HH:MM:SS → HH:MM:SS` `` 或 `` `MM:SS → MM:SS` ``（反引号包裹、`→` 分隔）
- 线上地址：`http://47.108.230.162/script/subtitles/`；服务器路径 `root@47.108.230.162:/www/wwwroot/47.108.230.162/script/subtitles/`
- 本地端口 8800；kit 面板 slug `subtitle-viewer`
- manifest.json 结构：`{"docs": [{"path", "title", "count", "duration"}]}`（path 为相对 src_root 的 posix 路径，duration 单位秒）
- UI 文案全部中文；代码注释风格照抄 speaking-player（简短中文 docstring）
- 提交信息格式：`feat(subtitle-viewer): ...` / `test(subtitle-viewer): ...`，结尾加 Co-Authored-By

## File Structure

```
tools/subtitle-viewer/
  tool.toml               # kit 面板注册（Task 1）
  package.json            # node --test 入口（Task 3）
  config.json             # {"src_root": "..."} 本地字幕根目录（Task 1）
  subtitle_lib.py         # Python 纯逻辑：收集含时间戳 md + manifest 条目（Task 1）
  fixtures/docs/…         # 样例字幕 md，本地预览与测试用（Task 2）
  dev_server.py           # 本地预览服务器（Task 2）
  core.js / core.test.js  # 前端纯逻辑：解析/对时/渲染辅助（Task 3、4）
  index.html / app.js / style.css   # UI（Task 5）
  sync_subtitles.py       # 一键发布到 47 服务器（Task 6）
  README.md               # 工具说明（Task 7）
tests/test_subtitle_viewer.py       # pytest（Task 1、2、6、7 增量）
README.md（仓库根）       # 工具表加一行（Task 7）
```

---

### Task 1: 工具骨架 + subtitle_lib 纯逻辑

**Files:**
- Create: `tools/subtitle-viewer/tool.toml`
- Create: `tools/subtitle-viewer/config.json`
- Create: `tools/subtitle-viewer/subtitle_lib.py`
- Test: `tests/test_subtitle_viewer.py`

**Interfaces:**
- Produces: `subtitle_lib.parse_ts(s: str) -> int`（秒）、`has_timestamps(text: str) -> bool`、`collect_docs(root: Path) -> list[dict]`（`[{"path","title","count","duration"}]`，path 为相对 root 的 posix，duration 秒）、`TS_RE`（时间戳正则）。Task 2/6 消费。

- [ ] **Step 1: 写失败测试**

```python
"""subtitle-viewer：subtitle_lib 纯逻辑 + dev_server + 面板清单发现。"""
import sys
from pathlib import Path

TOOL = Path(__file__).parents[1] / "tools" / "subtitle-viewer"
sys.path.insert(0, str(TOOL))


def test_parse_ts():
    from subtitle_lib import parse_ts
    assert parse_ts("00:00:06") == 6
    assert parse_ts("0:06") == 6
    assert parse_ts("01:02:03") == 3723
    assert parse_ts("62:05") == 3725


def test_has_timestamps():
    from subtitle_lib import has_timestamps
    assert has_timestamps("`00:00:00 → 00:00:06`")
    assert has_timestamps("前言\n\n`3:10 → 3:20`\n\n**a**\n")
    assert not has_timestamps("# 只有标题\n\n普通文本，没有时间戳。")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_subtitle_viewer.py -v`
Expected: FAIL `ModuleNotFoundError: No module named 'subtitle_lib'`

- [ ] **Step 3: 建骨架文件 + 最小实现**

`tools/subtitle-viewer/tool.toml`：

```toml
name = "字幕跟读器"
desc = "外部播放视频/音频时，手机打开字幕MD自动滚动跟读（手动对时，±5s 校准）"
category = "英语"
status = "ready"

[run]
cmd = ["python", "dev_server.py"]
port = 8800
url = "http://127.0.0.1:8800"

[links]
live = "http://47.108.230.162/script/subtitles/"
```

`tools/subtitle-viewer/config.json`（真实路径，随仓库提交）：

```json
{
  "src_root": "D:\\Users\\luocj\\Ahuaxi\\hcrs_devdocs\\ielts"
}
```

`tools/subtitle-viewer/subtitle_lib.py`：

```python
"""subtitle-viewer 纯逻辑：字幕 md 收集与 manifest 条目构建（sync / dev_server 共用）。"""
from __future__ import annotations

import re
from pathlib import Path

# `MM:SS → MM:SS` 或 `HH:MM:SS → HH:MM:SS`（反引号包裹，bilibili-subtitles 生成格式）
TS_RE = re.compile(r"`(\d{1,2}:\d{2}(?::\d{2})?)\s*→\s*(\d{1,2}:\d{2}(?::\d{2})?)`")


def parse_ts(s: str) -> int:
    """'00:00:06' / '0:06' -> 秒。"""
    parts = [int(x) for x in s.split(":")]
    if len(parts) == 3:
        h, m, sec = parts
        return h * 3600 + m * 60 + sec
    m, sec = parts
    return m * 60 + sec


def has_timestamps(text: str) -> bool:
    return TS_RE.search(text) is not None


def collect_docs(root: Path) -> list[dict]:
    """递归收集含时间戳的 .md（跳过 _ 开头的目录/文件），按相对路径排序返回 manifest 条目。"""
    root = Path(root)
    docs: list[dict] = []
    for p in sorted(root.rglob("*.md")):
        rel = p.relative_to(root)
        if any(part.startswith("_") for part in rel.parts):
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        stamps = TS_RE.findall(text)
        if not stamps:
            continue
        docs.append({
            "path": rel.as_posix(),
            "title": p.stem,
            "count": len(stamps),
            "duration": max(parse_ts(end) for _, end in stamps),
        })
    return docs
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_subtitle_viewer.py -v`
Expected: 2 PASS

- [ ] **Step 5: 补 collect_docs 测试（先失败）**

在 `tests/test_subtitle_viewer.py` 追加：

```python
GOOD_MD = "# 标题\n\n> 来源说明\n\n---\n\n`00:00:00 → 00:00:06`\n\n**Hello.**\n\n你好。\n\n---\n\n`00:00:08 → 00:00:14`\n\n**World.**\n\n世界。\n"


def test_collect_docs(tmp_path):
    from subtitle_lib import collect_docs
    (tmp_path / "in-use" ).mkdir()
    (tmp_path / "in-use" / "Unit 1.md").write_text(GOOD_MD, encoding="utf-8")
    (tmp_path / "plain.md").write_text("# 无时间戳\n", encoding="utf-8")
    (tmp_path / "_private").mkdir()
    (tmp_path / "_private" / "x.md").write_text(GOOD_MD, encoding="utf-8")

    docs = collect_docs(tmp_path)
    assert [d["path"] for d in docs] == ["in-use/Unit 1.md"]
    assert docs[0]["title"] == "Unit 1"
    assert docs[0]["count"] == 2
    assert docs[0]["duration"] == 14
```

Run: `python -m pytest tests/test_subtitle_viewer.py::test_collect_docs -v` → PASS（实现已在 Step 3 写全；若失败修实现）

- [ ] **Step 6: Commit**

```bash
git add tools/subtitle-viewer tests/test_subtitle_viewer.py
git commit -m "feat(subtitle-viewer): 工具骨架 + subtitle_lib 收集逻辑"
```

---

### Task 2: dev_server 本地预览

**Files:**
- Create: `tools/subtitle-viewer/fixtures/docs/in-use-advanced/Unit 1.md`（样例）
- Create: `tools/subtitle-viewer/fixtures/docs/collins/Listening.md`（样例，无时间戳，供降级测试）
- Create: `tools/subtitle-viewer/dev_server.py`
- Test: `tests/test_subtitle_viewer.py`（追加）

**Interfaces:**
- Consumes: `subtitle_lib.collect_docs`
- Produces: `resolve_docs_dir(cfg: Path, fallback: Path) -> Path`、`to_disk(url_path: str, docs_dir: Path) -> Path`；HTTP 行为：`/manifest.json` 动态 JSON、`/docs/**` 服务字幕文件、其余走静态。

- [ ] **Step 1: 建两个样例字幕**

`fixtures/docs/in-use-advanced/Unit 1.md`（真实格式样例，含头部 style/blockquote）：

```markdown
# Vocabulary in Use Advanced｜Unit 1（样例）

> 来源：https://www.bilibili.com/video/BVxxxx
> 字幕：English `faster-whisper small.en 机器识别` · 中文 `Google Translate 机器翻译` · 共 3 条

---

`00:00:00 → 00:00:06`

**Today we're diving into unit 1, cramming for success.**

今天我们将深入学习第一单元。

---

`00:00:08 → 00:00:14`

**Have you ever pulled an all-nighter before an exam?**

你有没有在考试前熬夜？

---

`00:00:14 → 00:00:20`

**Let's get the ball rolling.**

让我们开始吧。
```

`fixtures/docs/collins/Listening.md`：

```markdown
# 无时间戳样例

这一篇没有任何时间戳，打开时应降级为静态阅读模式。

---

**纯文本段落。**
```

- [ ] **Step 2: 写失败测试（追加到 tests/test_subtitle_viewer.py）**

```python
def test_resolve_docs_dir(tmp_path):
    from dev_server import resolve_docs_dir
    cfg = tmp_path / "config.json"
    real = tmp_path / "real"; real.mkdir()
    cfg.write_text('{"src_root": "%s"}' % str(real).replace("\\", "\\\\"), encoding="utf-8")
    assert resolve_docs_dir(cfg, tmp_path / "fallback") == real
    cfg.write_text('{"src_root": "Z:\\\\不存在的目录"}', encoding="utf-8")
    assert resolve_docs_dir(cfg, tmp_path / "fallback") == tmp_path / "fallback"
    assert resolve_docs_dir(tmp_path / "没有.json", tmp_path / "fallback") == tmp_path / "fallback"


def test_to_disk_maps_docs(tmp_path):
    from dev_server import to_disk
    assert to_disk("/docs/", tmp_path) == tmp_path
    assert to_disk("/docs", tmp_path) == tmp_path
    assert to_disk("/docs/a%20b.md", tmp_path) == tmp_path / "a b.md"
    assert to_disk("/").name == "index.html"
    assert to_disk("/manifest.json").name == "manifest.json"
```

- [ ] **Step 3: 跑测试确认失败**

Run: `python -m pytest tests/test_subtitle_viewer.py::test_resolve_docs_dir -v`
Expected: FAIL `ModuleNotFoundError: No module named 'dev_server'`

- [ ] **Step 4: 实现 dev_server.py**

```python
"""本地开发服务器：托管前端静态文件；/docs/** 映射本地字幕目录；/manifest.json 动态生成。

用法：python dev_server.py [port] [--lan]   # 默认 8800
"""
import json
import mimetypes
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from subtitle_lib import collect_docs

BASE = Path(__file__).resolve().parent


def resolve_docs_dir(cfg: Path = BASE / "config.json",
                     fallback: Path = BASE / "fixtures" / "docs") -> Path:
    """config.json 的 src_root 存在则用之，否则 fixtures。纯函数，可单测。"""
    if cfg.is_file():
        try:
            root = json.loads(cfg.read_text(encoding="utf-8")).get("src_root", "")
            if root and Path(root).is_dir():
                return Path(root)
        except (OSError, ValueError):
            pass
    return fallback


DOCS_DIR = resolve_docs_dir()


def to_disk(url_path: str, docs_dir: Path | None = None) -> Path:
    """URL -> 磁盘路径：/docs/** 映射字幕目录。纯函数，可单测。"""
    docs_dir = docs_dir if docs_dir is not None else DOCS_DIR
    rel = unquote(url_path).lstrip("/")
    if rel == "docs" or rel.startswith("docs/"):
        sub = rel[len("docs/"):] if rel.startswith("docs/") else ""
        return docs_dir / sub
    p = BASE / rel
    return p if p.suffix else BASE / "index.html"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/manifest.json":
            self._send_json({"docs": collect_docs(DOCS_DIR)})
            return
        disk = to_disk(path)
        if path.rstrip("/") == "/docs" or path.startswith("/docs/"):
            if disk.is_file():
                self._send_file(disk)
                return
            self.send_error(404, "Not Found")
            return
        if path == "/":
            disk = BASE / "index.html"
        if disk.is_file():
            self._send_file(disk)
            return
        self.send_error(404, "Not Found")

    def _send_json(self, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
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
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))


def lan_ip() -> str:
    """取本机局域网 IP（连不上外网时退化为主机名解析）。"""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return socket.gethostbyname(socket.gethostname())


def main(port=8800, lan=False):
    host = "0.0.0.0" if lan else "127.0.0.1"
    if lan:
        print(f"dev server on http://127.0.0.1:{port}/  and  http://{lan_ip()}:{port}/   (LAN，手机同一 Wi-Fi 可访问)")
    else:
        print(f"dev server on http://127.0.0.1:{port}/   (docs -> {DOCS_DIR})")
    HTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    argv = sys.argv[1:]
    lan = "--lan" in argv
    args = [a for a in argv if a != "--lan"]
    main(int(args[0]) if args else 8800, lan=lan)
```

- [ ] **Step 5: 跑测试确认通过**

Run: `python -m pytest tests/test_subtitle_viewer.py -v`
Expected: 全部 PASS

- [ ] **Step 6: Commit**

```bash
git add tools/subtitle-viewer tests/test_subtitle_viewer.py
git commit -m "feat(subtitle-viewer): dev_server 本地预览（docs 映射 + 动态 manifest）"
```

---

### Task 3: core.js 解析与对时

**Files:**
- Create: `tools/subtitle-viewer/package.json`
- Create: `tools/subtitle-viewer/core.js`
- Create: `tools/subtitle-viewer/core.test.js`

**Interfaces:**
- Produces（ES module exports）：`esc(s)`、`parseTs(s: str) -> ms:number`、`parseSubtitleMd(text) -> {blocks: [{startMs, endMs, en, zh, tsLabel}], hasTimestamps: boolean}`、`currentBlockIndex(blocks, ms) -> number`（间隙保持上一块，首块前 −1）、`isEnded(blocks, ms) -> boolean`、`class SyncClock`（`new SyncClock(nowFn)`；`start(atMs=0)`、`elapsedMs`、`shift(deltaMs)`、`anchorTo(targetMs)`、`pause()`、`resume()`、`paused`）、`formatMs(ms) -> "M:SS" | "H:MM:SS"`。Task 4/5 消费。

- [ ] **Step 1: package.json**

```json
{
  "name": "subtitle-viewer",
  "private": true,
  "type": "module",
  "scripts": { "test": "node --test" }
}
```

- [ ] **Step 2: 写失败测试 core.test.js**

```js
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  parseTs, parseSubtitleMd, currentBlockIndex, isEnded, SyncClock, formatMs,
} from "./core.js";

const MD = [
  "# 标题",
  "> 来源：xxx",
  "<style>p{font-size:18px}</style>",
  "",
  "---",
  "",
  "`00:00:00 → 00:00:06`",
  "",
  "**Hello world.**",
  "",
  "你好，世界。",
  "",
  "---",
  "",
  "`3:10 → 3:20`",
  "",
  "**Second block.**",
  "",
  "第二块。",
].join("\n");

test("parseTs 两种格式", () => {
  assert.equal(parseTs("00:00:06"), 6000);
  assert.equal(parseTs("0:06"), 6000);
  assert.equal(parseTs("01:02:03"), 3723000);
  assert.equal(parseTs("3:10"), 190000);
});

test("parseSubtitleMd 标准文档（头部跳过/两种时间戳/rn）", () => {
  const { blocks, hasTimestamps } = parseSubtitleMd(MD.replace(/\n/g, "\r\n"));
  assert.equal(hasTimestamps, true);
  assert.equal(blocks.length, 2);
  assert.deepEqual(blocks[0], {
    startMs: 0, endMs: 6000, en: "Hello world.", zh: "你好，世界。", tsLabel: "00:00:00 → 00:00:06",
  });
  assert.equal(blocks[1].startMs, 190000);
  assert.equal(blocks[1].endMs, 200000);
});

test("parseSubtitleMd 无时间戳降级", () => {
  const { blocks, hasTimestamps } = parseSubtitleMd("# 笔记\n\n普通段落。\n\n---\n\n**加粗**\n");
  assert.equal(hasTimestamps, false);
  assert.deepEqual(blocks, []);
});

test("currentBlockIndex 命中/间隙/首块前/空", () => {
  const B = [{ startMs: 0, endMs: 6000 }, { startMs: 8000, endMs: 14000 }];
  assert.equal(currentBlockIndex(B, 3000), 0);
  assert.equal(currentBlockIndex(B, 7000), 0);      // 间隙保持上一块
  assert.equal(currentBlockIndex(B, 9000), 1);
  assert.equal(currentBlockIndex(B, -1), -1);        // 首块前
  assert.equal(currentBlockIndex([], 1000), -1);
});

test("isEnded", () => {
  const B = [{ startMs: 0, endMs: 6000 }, { startMs: 8000, endMs: 14000 }];
  assert.equal(isEnded(B, 13999), false);
  assert.equal(isEnded(B, 14000), true);
  assert.equal(isEnded([], 999), false);
});

test("SyncClock 计时/暂停/±5s/锚定", () => {
  let t = 100000;
  const c = new SyncClock(() => t);
  assert.equal(c.elapsedMs, 0);                      // 未 start
  c.start(0);
  t = 100500;
  assert.equal(c.elapsedMs, 500);
  c.pause();
  t = 101000;
  assert.equal(c.elapsedMs, 500);                    // 暂停期间不走
  c.resume();
  t = 101200;
  assert.equal(c.elapsedMs, 700);
  c.shift(5000);
  assert.equal(c.elapsedMs, 5700);                   // +5s
  c.shift(-10000);
  assert.equal(c.elapsedMs, 0);                      // 负数钳到 0
  t = 101300;
  c.anchorTo(190000);                                // 锚定到 3:10
  t = 101400;
  assert.equal(c.elapsedMs, 190100);
});

test("formatMs", () => {
  assert.equal(formatMs(0), "0:00");
  assert.equal(formatMs(83000), "1:23");
  assert.equal(formatMs(3723000), "1:02:03");
  assert.equal(formatMs(-5), "0:00");
});

```

- [ ] **Step 3: 跑测试确认失败**

Run: `cd tools/subtitle-viewer && node --test`
Expected: FAIL（找不到 ./core.js）

- [ ] **Step 4: 实现 core.js（解析 + 对时部分）**

```js
// subtitle-viewer/core.js
// 纯逻辑 + 渲染辅助，无副作用（无 DOM / 网络），node:test 单测。

export function esc(s) {
  return String(s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

const TS_RE = /^`(\d{1,2}:\d{2}(?::\d{2})?)\s*→\s*(\d{1,2}:\d{2}(?::\d{2})?)`$/;

export function parseTs(s) {
  const p = s.split(":").map(Number);
  return p.length === 3
    ? ((p[0] * 60 + p[1]) * 60 + p[2]) * 1000
    : (p[0] * 60 + p[1]) * 1000;
}

export function parseSubtitleMd(text) {
  const blocks = [];
  const chunks = String(text).replace(/\r\n/g, "\n").split(/\n-{3,}\n/);
  for (const chunk of chunks) {
    const lines = chunk.split("\n").map((l) => l.trim()).filter(Boolean);
    const tsLine = lines.find((l) => TS_RE.test(l));
    if (!tsLine) continue;                          // 头部/无时间戳块：跳过
    const m = tsLine.match(TS_RE);
    const en = lines
      .filter((l) => /^\*\*.+\*\*$/.test(l))
      .map((l) => l.replace(/^\*\*/, "").replace(/\*\*$/, ""))
      .join(" ");
    const zh = lines
      .filter((l) => l !== tsLine && !/^\*\*.+\*\*$/.test(l))
      .join("\n");
    blocks.push({
      startMs: parseTs(m[1]), endMs: parseTs(m[2]), en, zh,
      tsLabel: m[0].slice(1, -1),
    });
  }
  return { blocks, hasTimestamps: blocks.length > 0 };
}

export function currentBlockIndex(blocks, ms) {
  let ans = -1;
  for (let i = 0; i < blocks.length; i++) {
    if (blocks[i].startMs <= ms) ans = i; else break;
  }
  return ans;
}

export function isEnded(blocks, ms) {
  return blocks.length > 0 && ms >= blocks[blocks.length - 1].endMs;
}

export class SyncClock {
  constructor(now = () => performance.now()) {
    this._now = now;
    this._t0 = null;        // 启动参考点
    this._offsetMs = 0;     // 锚定初值 + ±5s 累计
    this._pausedTotal = 0;  // 累计暂停时长
    this._pausedAt = null;
  }
  get paused() { return this._pausedAt !== null; }
  start(atMs = 0) {
    this._t0 = this._now();
    this._offsetMs = atMs;
    this._pausedTotal = 0;
    this._pausedAt = null;
  }
  get elapsedMs() {
    if (this._t0 === null) return 0;
    const ref = this._pausedAt ?? this._now();
    return Math.max(0, this._offsetMs + (ref - this._t0) - this._pausedTotal);
  }
  shift(deltaMs) { this._offsetMs += deltaMs; }
  anchorTo(targetMs) {   // 让 elapsed 立即等于 targetMs（重置参考点）
    this._t0 = this._now();
    this._offsetMs = targetMs;
    this._pausedTotal = 0;
    if (this._pausedAt !== null) this._pausedAt = this._now();
  }
  pause() { if (this._t0 !== null && !this.paused) this._pausedAt = this._now(); }
  resume() {
    if (this.paused) {
      this._pausedTotal += this._now() - this._pausedAt;
      this._pausedAt = null;
    }
  }
}

export function formatMs(ms) {
  if (!Number.isFinite(ms) || ms < 0) ms = 0;
  const t = Math.floor(ms / 1000);
  const h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), s = t % 60;
  return h > 0
    ? `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`
    : `${m}:${String(s).padStart(2, "0")}`;
}
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd tools/subtitle-viewer && node --test`
Expected: 6 test 全 PASS

- [ ] **Step 6: Commit**

```bash
git add tools/subtitle-viewer
git commit -m "feat(subtitle-viewer): core.js 解析与手动对时（SyncClock）"
```

---

### Task 4: core.js 渲染辅助

**Files:**
- Modify: `tools/subtitle-viewer/core.js`（追加导出）
- Modify: `tools/subtitle-viewer/core.test.js`（追加测试）

**Interfaces:**
- Consumes: `esc`（Task 3）
- Produces: `renderBlock(block, i, active) -> html string`（`<section class="blk" data-i>` + `<button class="ts">` + `<p class="en">` + `<p class="zh">`）、`groupManifest(docs) -> [{dir, items}]`（dir 为 posix 目录名，根目录用 `"字幕"`）。Task 5 消费。

- [ ] **Step 1: 追加失败测试**

```js
import { renderBlock, groupManifest } from "./core.js";   // 追加到文件头 import

test("renderBlock 转义与结构", () => {
  const b = { startMs: 0, endMs: 6, en: "A<B>&C", zh: "甲&乙", tsLabel: "00:00:00 → 00:00:06" };
  const html = renderBlock(b, 3, false);
  assert.ok(html.includes('class="blk" data-i="3"'));
  assert.ok(html.includes('<button class="ts"'));
  assert.ok(html.includes("A&lt;B&gt;&amp;C"));
  assert.ok(html.includes("甲&amp;乙"));
  const on = renderBlock(b, 3, true);
  assert.ok(on.includes('class="blk is-on"'));
  const noZh = renderBlock({ ...b, zh: "" }, 0, false);
  assert.ok(!noZh.includes('class="zh"'));
});

test("groupManifest 按目录分组", () => {
  const groups = groupManifest([
    { path: "in-use/Unit 1.md", title: "Unit 1", count: 3, duration: 20 },
    { path: "collins/A.md", title: "A", count: 2, duration: 14 },
    { path: "root.md", title: "root", count: 1, duration: 6 },
  ]);
  // 空串目录（根目录）排序在最前，显示名替换为「字幕」
  assert.deepEqual(groups.map((g) => g.dir), ["字幕", "collins", "in-use"]);
  assert.equal(groups[0].items.length, 1);
});
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd tools/subtitle-viewer && node --test`
Expected: 新增 2 test FAIL（export 不存在）

- [ ] **Step 3: core.js 追加实现**

```js
export function renderBlock(b, i, active) {
  return (
    `<section class="blk${active ? " is-on" : ""}" data-i="${i}">` +
    `<button class="ts" data-i="${i}">${esc(b.tsLabel)}</button>` +
    `<p class="en">${esc(b.en)}</p>` +
    (b.zh ? `<p class="zh">${esc(b.zh)}</p>` : "") +
    `</section>`
  );
}

export function groupManifest(docs) {
  const map = new Map();
  for (const d of docs) {
    const dir = d.path.includes("/") ? d.path.slice(0, d.path.lastIndexOf("/")) : "";
    if (!map.has(dir)) map.set(dir, []);
    map.get(dir).push(d);
  }
  return [...map.entries()]
    .sort((a, b) => a[0].localeCompare(b[0], "zh-CN"))
    .map(([dir, items]) => ({ dir: dir || "字幕", items }));
}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd tools/subtitle-viewer && node --test`
Expected: 全 PASS

- [ ] **Step 5: Commit**

```bash
git add tools/subtitle-viewer
git commit -m "feat(subtitle-viewer): core.js 渲染辅助（块渲染/目录分组）"
```

---

### Task 5: 前端 UI（index.html / app.js / style.css）

**Files:**
- Create: `tools/subtitle-viewer/index.html`
- Create: `tools/subtitle-viewer/app.js`
- Create: `tools/subtitle-viewer/style.css`

**Interfaces:**
- Consumes: Task 3/4 的全部导出；`manifest.json`（`{"docs":[...]}`）与 `docs/<rel>.md` 两个 HTTP 资源。
- Produces: 可用页面。无自动测试（逻辑已在 core.js 覆盖），本任务以手动验收清单收尾。

- [ ] **Step 1: index.html**

```html
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>字幕跟读器</title>
<link rel="stylesheet" href="style.css">
</head>
<body>
  <header id="topbar">
    <button id="back" hidden>‹ 列表</button>
    <h1 id="app-title">字幕跟读器</h1>
    <h1 id="doc-title" hidden></h1>
    <span id="clock" hidden>0:00</span>
  </header>

  <main id="list"></main>

  <main id="doc" hidden>
    <div id="blocks"></div>
    <button id="back-cur" hidden>↓ 回到当前</button>
    <div id="controls">
      <button id="minus5">−5s</button>
      <button id="playpause" aria-label="暂停/继续">⏸</button>
      <button id="plus5">+5s</button>
    </div>
    <div id="ended" hidden>字幕已结束</div>
  </main>

  <div id="standby" hidden>
    <button id="standby-btn">▶<small>视频开始时点这里</small></button>
  </div>

<script type="module" src="app.js"></script>
</body>
</html>
```

- [ ] **Step 2: app.js（副作用层）**

```js
// subtitle-viewer/app.js —— 副作用层：fetch / DOM / 计时 / 滚动。逻辑全在 core.js。
import {
  esc, parseSubtitleMd, currentBlockIndex, isEnded, SyncClock, formatMs,
  renderBlock, groupManifest,
} from "./core.js";

const $ = (sel) => document.querySelector(sel);

const state = {
  clock: new SyncClock(),
  blocks: [],
  follow: true,
  ended: false,
  activeIdx: -1,
  timer: null,
  wakeLock: null,
};

/* ---------- 列表视图 ---------- */

async function loadManifest() {
  let manifest = { docs: [] };
  try {
    const res = await fetch("manifest.json");
    if (res.ok) manifest = await res.json();
  } catch { /* 网络失败 → 空列表提示 */ }
  renderList(manifest.docs || []);
}

function renderList(docs) {
  if (!docs.length) {
    $("#list").innerHTML =
      `<p class="empty">还没有字幕。先在电脑上跑 <code>python sync_subtitles.py</code> 上传。</p>`;
    return;
  }
  $("#list").innerHTML = groupManifest(docs).map((g) =>
    `<h2 class="group">${esc(g.dir)}</h2><ul class="docs">` +
    g.items.map((d) =>
      `<li><a class="doc" href="?doc=${encodeURIComponent(d.path)}">` +
      `<span class="doc-title">${esc(d.title)}</span>` +
      `<span class="doc-meta">${d.count} 条 · ${formatMs(d.duration * 1000)}</span>` +
      `</a></li>`).join("") +
    `</ul>`).join("");
}

/* ---------- 字幕视图 ---------- */

async function openDoc(rel) {
  let text;
  try {
    const url = "docs/" + rel.split("/").map(encodeURIComponent).join("/");
    const res = await fetch(url);
    if (!res.ok) throw new Error(res.status);
    text = await res.text();
  } catch {
    alert("字幕加载失败，请重试");
    location.href = location.pathname;
    return;
  }
  $("#doc-title").textContent = rel.split("/").pop().replace(/\.md$/i, "");
  const parsed = parseSubtitleMd(text);
  state.blocks = parsed.blocks;

  if (!parsed.hasTimestamps) return enterStaticMode(text);
  $("#blocks").innerHTML = state.blocks.map((b, i) => renderBlock(b, i, false)).join("");
  enterStandby();
}

function enterStaticMode(text) {
  $("#controls").hidden = true;
  $("#clock").hidden = true;
  $("#blocks").classList.add("static");
  $("#blocks").innerHTML = text.replace(/\r\n/g, "\n").split(/\n-{3,}\n/)
    .map((c) => c.trim()).filter(Boolean)
    .map((c) => `<section class="blk"><p class="en">${esc(c)}</p></section>`).join("");
}

function enterStandby() {
  $("#standby").hidden = false;
  $("#standby-btn").addEventListener("click", startFollowing, { once: true });
}

function startFollowing() {
  $("#standby").hidden = true;
  state.clock.start(0);
  state.timer = setInterval(tick, 500);
  tick();
  keepAwake(true);
}

function tick() {
  const ms = state.clock.elapsedMs;
  $("#clock").textContent = formatMs(ms);
  if (isEnded(state.blocks, ms)) {
    if (!state.ended) { state.ended = true; $("#ended").hidden = false; }
    return;
  }
  state.ended = false;
  $("#ended").hidden = true;
  const idx = currentBlockIndex(state.blocks, ms);
  if (idx !== state.activeIdx) {
    setActive(idx);
    if (state.follow) scrollToActive();
  }
}

function setActive(idx) {
  const prev = document.querySelector(".blk.is-on");
  if (prev) prev.classList.remove("is-on");
  state.activeIdx = idx;
  const el = document.querySelector(`.blk[data-i="${idx}"]`);
  if (el) el.classList.add("is-on");
}

function scrollToActive() {
  document.querySelector(`.blk[data-i="${state.activeIdx}"]`)
    ?.scrollIntoView({ behavior: "smooth", block: "center" });
}

/* ---------- 交互 ---------- */

$("#back").addEventListener("click", () => { location.href = location.pathname; });

$("#minus5").addEventListener("click", () => state.clock.shift(-5000));
$("#plus5").addEventListener("click", () => state.clock.shift(5000));

$("#playpause").addEventListener("click", () => {
  if (state.clock.paused) { state.clock.resume(); $("#playpause").textContent = "⏸"; }
  else { state.clock.pause(); $("#playpause").textContent = "▶"; }
});

$("#blocks").addEventListener("click", (e) => {           // 点时间戳 → 锚定
  const btn = e.target.closest(".ts");
  if (!btn || !state.timer) return;
  const i = Number(btn.dataset.i);
  state.clock.anchorTo(state.blocks[i].startMs);
  state.follow = true;
  $("#back-cur").hidden = true;
  setActive(i);
  scrollToActive();
});

$("#back-cur").addEventListener("click", () => {
  state.follow = true;
  $("#back-cur").hidden = true;
  scrollToActive();
});

/* 用户手指拖动/滚轮 → 暂停跟随（scrollIntoView 不触发这两个事件） */
for (const ev of ["touchmove", "wheel"]) {
  document.addEventListener(ev, () => {
    if (state.timer && state.follow && !state.ended) {
      state.follow = false;
      $("#back-cur").hidden = false;
    }
  }, { passive: true });
}

/* ---------- 屏幕常亮（失败静默降级） ---------- */

async function keepAwake(on) {
  try {
    if (on && "wakeLock" in navigator) {
      state.wakeLock = await navigator.wakeLock.request("screen");
    } else {
      await state.wakeLock?.release();
      state.wakeLock = null;
    }
  } catch { state.wakeLock = null; }
}
document.addEventListener("visibilitychange", () => {
  if (state.timer) keepAwake(!document.hidden);
});

/* ---------- 路由 ---------- */

const doc = new URLSearchParams(location.search).get("doc");
if (doc) {
  $("#list").hidden = true;
  $("#doc").hidden = false;
  $("#back").hidden = false;
  $("#app-title").hidden = true;
  $("#doc-title").hidden = false;
  $("#clock").hidden = false;
  openDoc(doc);
} else {
  loadManifest();
}
```

- [ ] **Step 3: style.css**

```css
:root {
  --fg: #1f2328; --muted: #6a737d; --bg: #ffffff; --card: #f6f8fa;
  --accent: #0969da; --accent-soft: #ddf4ff;
}
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body {
  margin: 0; color: var(--fg); background: var(--bg);
  font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
  line-height: 1.6;
}

/* 顶栏 */
#topbar {
  position: sticky; top: 0; z-index: 10;
  display: flex; align-items: center; gap: 12px;
  padding: 10px 16px; background: var(--bg);
  border-bottom: 1px solid #eaeef2;
}
#topbar h1 { font-size: 17px; margin: 0; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
#clock { font-variant-numeric: tabular-nums; color: var(--accent); font-weight: 600; }
#back { border: none; background: none; color: var(--accent); font-size: 16px; padding: 4px; }

/* 列表 */
#list { max-width: 720px; margin: 0 auto; padding: 12px 16px 40px; }
.group { font-size: 14px; color: var(--muted); margin: 22px 0 8px; }
.docs { list-style: none; margin: 0; padding: 0; }
.doc {
  display: flex; justify-content: space-between; align-items: baseline; gap: 12px;
  padding: 12px 14px; margin-bottom: 8px; border-radius: 10px;
  background: var(--card); color: var(--fg); text-decoration: none;
}
.doc-title { font-size: 15px; }
.doc-meta { font-size: 12px; color: var(--muted); white-space: nowrap; }
.empty { color: var(--muted); text-align: center; margin-top: 40vh; }
.empty code { background: var(--card); padding: 2px 6px; border-radius: 6px; }

/* 字幕块 */
#doc { max-width: 720px; margin: 0 auto; padding: 12px 16px 120px; }
.blk { padding: 14px 12px; border-radius: 12px; border-left: 4px solid transparent; }
.blk .ts {
  border: none; background: none; padding: 0; font-size: 12px;
  color: var(--muted); font-variant-numeric: tabular-nums; cursor: pointer;
}
.blk .en { font-size: 19px; font-weight: 600; margin: 6px 0 4px; }
.blk .zh { font-size: 14px; color: var(--muted); margin: 0; }
.blk.is-on {
  background: var(--accent-soft);
  border-left-color: var(--accent);
}
#blocks.static .blk { background: var(--card); margin-bottom: 10px; }

/* 底部控制条 */
#controls {
  position: fixed; left: 50%; transform: translateX(-50%);
  bottom: max(16px, env(safe-area-inset-bottom)); z-index: 10;
  display: flex; gap: 10px;
}
#controls button {
  min-width: 64px; padding: 12px 18px; border-radius: 999px; border: none;
  background: var(--fg); color: #fff; font-size: 16px;
}
#back-cur {
  position: fixed; right: 16px; bottom: 84px; z-index: 10;
  padding: 10px 14px; border-radius: 999px; border: none;
  background: var(--accent); color: #fff; font-size: 14px;
}
#ended {
  position: fixed; top: 60px; left: 50%; transform: translateX(-50%);
  padding: 8px 16px; border-radius: 999px;
  background: var(--fg); color: #fff; font-size: 14px;
}

/* 待命遮罩 */
#standby {
  position: fixed; inset: 0; z-index: 20;
  display: flex; align-items: center; justify-content: center;
  background: rgba(255, 255, 255, 0.96);
}
#standby-btn {
  display: flex; flex-direction: column; align-items: center; gap: 8px;
  width: 220px; height: 220px; border-radius: 50%; border: none;
  background: var(--accent); color: #fff; font-size: 56px;
}
#standby-btn small { font-size: 14px; font-weight: 500; }
```

- [ ] **Step 4: 手动验收（本地）**

```bash
cd tools/subtitle-viewer && python dev_server.py
```

浏览器 `http://127.0.0.1:8800` 验收清单：
1. 列表出现 fixtures 里的 `in-use-advanced/Unit 1.md`（3 条 · 0:20）；`collins/Listening.md` 也在
2. 点 Unit 1 → 待命大按钮出现；点「▶」→ 计时开始，第一块高亮居中
3. +5s/-5s 生效（时钟跳变、高亮块切换）
4. 点某块时间戳 → 立即锚定到该块
5. ⏸ 暂停后时钟不走，▶ 恢复
6. 手动滚轮上翻 → 出现「↓ 回到当前」，点击回跟
7. 点 collins/Listening → 无控制条、静态阅读模式
8. `?doc=in-use-advanced%2FUnit%201.md` 直达正常
9. 20 秒后出现「字幕已结束」

- [ ] **Step 5: Commit**

```bash
git add tools/subtitle-viewer
git commit -m "feat(subtitle-viewer): 前端 UI（列表/待命对时/跟随滚动/静态降级）"
```

---

### Task 6: sync_subtitles 一键发布

**Files:**
- Create: `tools/subtitle-viewer/sync_subtitles.py`
- Test: `tests/test_subtitle_viewer.py`（追加）

**Interfaces:**
- Consumes: `subtitle_lib.collect_docs`；`config.json` 的 `src_root`
- Produces: `front_files(tool_dir) -> list[Path]`、`default_src() -> Path`；CLI 行为：`python sync_subtitles.py [--src 目录] [--dry-run]`。

- [ ] **Step 1: 写失败测试（追加）**

```python
def test_sync_front_files_and_read_src(tmp_path):
    import sync_subtitles
    files = sync_subtitles.front_files(TOOL)
    assert [f.name for f in files] == ["index.html", "app.js", "core.js", "style.css"]

    cfg = tmp_path / "config.json"
    real = tmp_path / "real"; real.mkdir()
    cfg.write_text('{"src_root": "%s"}' % str(real).replace("\\", "\\\\"), encoding="utf-8")
    assert sync_subtitles.read_src(cfg) == real
    assert sync_subtitles.read_src(tmp_path / "没有.json") == TOOL / "fixtures" / "docs"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_subtitle_viewer.py::test_sync_front_files_and_default_src -v`
Expected: FAIL `No module named 'sync_subtitles'`

- [ ] **Step 3: 实现 sync_subtitles.py**

```python
"""一键同步：本地字幕 md 目录 → 服务器 subtitles 站点。

用法：python sync_subtitles.py [--src 目录] [--dry-run]
默认源目录读 config.json 的 src_root。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from subtitle_lib import collect_docs

TOOL_DIR = Path(__file__).resolve().parent
REMOTE_HOST = "root@47.108.230.162"
REMOTE_BASE = "/www/wwwroot/47.108.230.162/script/subtitles"
FRONT_NAMES = ("index.html", "app.js", "core.js", "style.css")


def front_files(tool_dir: Path) -> list[Path]:
    """要上传的前端静态文件（存在的才算）。"""
    return [tool_dir / n for n in FRONT_NAMES if (tool_dir / n).is_file()]


def read_src(cfg: Path = TOOL_DIR / "config.json") -> Path:
    """config.json 的 src_root；缺失/无效则回退 fixtures/docs。纯函数，可单测。"""
    if cfg.is_file():
        try:
            root = json.loads(cfg.read_text(encoding="utf-8")).get("src_root", "")
            if root:
                return Path(root)
        except (OSError, ValueError):
            pass
    return TOOL_DIR / "fixtures" / "docs"


def run(cmd: list[str], dry: bool) -> None:
    printable = " ".join(str(c) for c in cmd)
    print("$", printable)
    if not dry:
        subprocess.run(cmd, check=True)


def upload(remote: str, local: Path, dry: bool) -> None:
    run(["scp", str(local), f"{REMOTE_HOST}:{remote}"], dry)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="同步字幕与前端到服务器")
    ap.add_argument("--src", type=Path, default=None, help="本地字幕目录（默认读 config.json）")
    ap.add_argument("--dry-run", action="store_true", help="只打印命令不执行")
    args = ap.parse_args(argv)
    src = args.src or read_src()

    docs = collect_docs(src)
    if not docs:
        sys.exit(f"源目录没有含时间戳的 md：{src}")

    fronts = front_files(TOOL_DIR)
    run(["ssh", REMOTE_HOST, f"mkdir -p {REMOTE_BASE}/docs"], args.dry_run)
    for f in fronts:
        upload(f"{REMOTE_BASE}/", f, args.dry_run)
    for d in docs:
        rel = Path(d["path"])
        if str(rel.parent) != ".":
            run(["ssh", REMOTE_HOST, f"mkdir -p {REMOTE_BASE}/docs/{rel.parent.as_posix()}"], args.dry_run)
        upload(f"{REMOTE_BASE}/docs/{rel.as_posix()}", src / rel, args.dry_run)

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump({"docs": docs}, f, ensure_ascii=False, indent=2)
        manifest_tmp = f.name
    upload(f"{REMOTE_BASE}/manifest.json", Path(manifest_tmp), args.dry_run)
    run(["ssh", REMOTE_HOST, f"chown -R www:www {REMOTE_BASE}"], args.dry_run)
    print(f"完成：{len(fronts)} 个前端文件 + {len(docs)} 篇字幕")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑全部测试确认通过**

Run: `python -m pytest tests/test_subtitle_viewer.py -v`
Expected: 全 PASS

- [ ] **Step 5: dry-run 冒烟**

Run: `cd tools/subtitle-viewer && python sync_subtitles.py --src fixtures/docs --dry-run`
Expected: 打印 scp/ssh 命令清单（不执行），结尾「完成：4 个前端文件 + N 篇字幕」

- [ ] **Step 6: Commit**

```bash
git add tools/subtitle-viewer tests/test_subtitle_viewer.py
git commit -m "feat(subtitle-viewer): sync_subtitles 一键发布（md+前端+manifest）"
```

---

### Task 7: 面板注册验证 + README 收尾

**Files:**
- Modify: `tests/test_subtitle_viewer.py`（追加）
- Create: `tools/subtitle-viewer/README.md`
- Modify: `README.md`（仓库根，工具表加一行）

**Interfaces:**
- Consumes: Task 1 的 `tool.toml`；launcher 的 `load_tools`。

- [ ] **Step 1: 追加面板发现测试（tool.toml 在 Task 1 已建，此处为验证性测试，直接应 PASS）**

```python
def test_manifest_discovers_subtitle_viewer():
    sys.path.insert(0, str(Path(__file__).parents[1]))
    from launcher.manifest import load_tools

    tools = {t.slug: t for t in load_tools(Path(__file__).parents[1] / "tools")}
    assert tools["subtitle-viewer"].port == 8800
    assert tools["subtitle-viewer"].status == "ready"
```

Run: `python -m pytest tests/test_subtitle_viewer.py::test_manifest_discovers_subtitle_viewer -v` → PASS（若 FAIL 检查 tool.toml 是否在 Task 1 正确创建）

- [ ] **Step 2: 工具 README**

`tools/subtitle-viewer/README.md`：

```markdown
# 字幕跟读器（subtitle-viewer）

外部播放视频/音频（手机 B站App、电脑任意播放器）时，手机浏览器打开本页，
选对应字幕 MD，点「▶ 视频开始时点这里」开始对时——页面按时钟自动滚动高亮当前句。
不检测外部播放器进度；±5s 按钮校准，点任意时间戳重新锚定（视频拖动后用），⏸ 与视频同停。

## 本地预览
cd subtitle-viewer && python dev_server.py    # http://127.0.0.1:8800（docs 读 config.json 的 src_root，无则 fixtures）
手机同 Wi-Fi 预览：python dev_server.py --lan

## 部署与同步
python sync_subtitles.py [--src 目录] [--dry-run]
线上：http://47.108.230.162/script/subtitles/
源目录默认 config.json 的 src_root；只上传含时间戳的 md（bilibili-subtitles 生成格式）。

## 字幕 md 格式
块间 `---` 分隔；每块：`00:00:08 → 00:00:14`（反引号）+ `**英文**` + 中文段落。
无时间戳的 md 降级为静态阅读模式。

## 测试
node --test                       # core.js 纯逻辑
pytest tests/test_subtitle_viewer.py
```

- [ ] **Step 3: 根 README 工具表加一行（Word→Markdown 行之后）**

```markdown
| 字幕跟读器 | 外部播放视频时手机滚动跟读字幕 MD（手动对时 ±5s 校准；线上 http://47.108.230.162/script/subtitles/ ） | http://127.0.0.1:8800 |
```

- [ ] **Step 4: 全量回归**

Run: `python -m pytest tests/ -q && cd tools/subtitle-viewer && node --test`
Expected: 全 PASS（不影响其他工具测试）

- [ ] **Step 5: Commit**

```bash
git add tools/subtitle-viewer/README.md README.md tests/test_subtitle_viewer.py
git commit -m "docs(subtitle-viewer): README + 面板注册验证"
```

---

## 真机验收（全部任务完成后，用户手动）

1. 电脑上 `cd tools/subtitle-viewer && python sync_subtitles.py`（真实上传）
2. 手机开 B站 App 播放对应视频（后台音频）
3. 手机浏览器开 `http://47.108.230.162/script/subtitles/`，点对应字幕，视频开始时点「▶」
4. 验证滚动跟随、±5s、锚定、暂停、屏幕常亮
