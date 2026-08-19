# speaking-player 卡拉OK跟读播放器 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** text2mp3 生成的口语 MP3 带词级时间轴上服务器，网页（重点手机）卡拉OK式逐词高亮跟读，支持单句循环/倍速/中文翻译。

**Architecture:** 生成端（text2mp3）流式收集 edge-tts `WordBoundary` 事件，MP3 落地时同写同名 timeline `.json`；`sync_speaking.py` 全量 scp 到服务器 `47.108.230.162` 的 `/script/speaking/`；播放端是纯静态 4 文件页（对齐 audio-player 模式），nginx `autoindex json` 发现曲目，`requestAnimationFrame` 对照 `audio.currentTime` 逐词高亮。

**Tech Stack:** Python 3.12（edge-tts 7.2.8 已装、Flask）、原生 ESM JS（node:test 单测，零构建零依赖）、nginx autoindex json、scp/ssh。

**Spec:** `docs/superpowers/specs/2026-08-19-speaking-player-design.md`

## Global Constraints

- 分支 `feature/speaking-player` 上开发；每个 Task 一次 commit
- timeline json 时间单位一律**毫秒**；`words[i] = {t, s, d}`，`sentences[k] = {text, i, j, start, end}`（i/j 为 words 下标闭区间）
- MP3 与 json 同名配对（`X.mp3` + `X.json`）；无 json → 播放器降级为无字幕播放，不报错
- JS：ESM、无构建、无外部依赖；纯逻辑进 `core.js`（node --test），DOM/网络只进 `app.js`
- Python 纯逻辑可离线单测（不联网）；真实合成只做手动 E2E
- 端口：text2mp3 8300 已用，speaking-player 本地预览用 **8400**
- 服务器：`root@47.108.230.162`，静态根 `/www/wwwroot/47.108.230.162/script/`，新目录 `speaking/`（内含 `tracks/`）
- 代码与注释风格对齐 `tools/audio-player`（中文注释、`$()` 取元素、state 对象、bind() 绑事件）

---

### Task 1: timeline 数据结构（tts_core.build_timeline + json 写出）

**Files:**
- Modify: `tools/text2mp3/tts_core.py`（文件末尾追加）
- Test: `tests/test_text2mp3.py`（追加）

**Interfaces:**
- Produces:
  - `split_sentences_text(text: str) -> list[str]` — 按句末标点切原文
  - `build_timeline(events: list[dict], text: str = "", voice: str = "", rate: str = "+0%", pitch: str = "+0Hz", translation: str = "") -> dict` — events 为 edge-tts stream 事件列表（dict 含 `type/text/offset/duration`，offset/duration 为 100ns 单位）；返回 `{"voice","rate","pitch","words","sentences","translation"}`
  - `timeline_path(mp3_path: Path) -> Path`、`write_timeline(mp3_path: Path, timeline: dict) -> Path`

- [ ] **Step 1: 写失败测试**

在 `tests/test_text2mp3.py` 追加：

```python
def _ev(text, offset_100ns, dur_100ns):
    return {"type": "WordBoundary", "text": text, "offset": offset_100ns, "duration": dur_100ns}


def test_split_sentences_text():
    text = "To me, English is a bridge. It's magical! Isn't it?"
    assert core.split_sentences_text(text) == [
        "To me, English is a bridge.", "It's magical!", "Isn't it?",
    ]
    assert core.split_sentences_text("  ") == []


def test_build_timeline_units_and_sentences():
    events = [
        _ev("To", 0, 2_100_000),           # s=0ms d=210ms
        _ev("me,", 240_000, 180_000),      # s=24ms d=18ms
        _ev("world.", 500_000, 300_000),   # s=50ms d=30ms
    ]
    tl = core.build_timeline(events, text="To me, world.",
                             voice="v1", rate="-10%", pitch="+0Hz", translation="译")
    assert tl["words"] == [
        {"t": "To", "s": 0, "d": 210},
        {"t": "me,", "s": 24, "d": 18},
        {"t": "world.", "s": 50, "d": 30},
    ]
    # 一句（token 数 3 = 词数 3），覆盖全部词
    assert len(tl["sentences"]) == 1
    s = tl["sentences"][0]
    assert (s["i"], s["j"]) == (0, 2)
    assert s["start"] == 0 and s["end"] == 80   # 50+30
    assert tl["translation"] == "译" and tl["voice"] == "v1"


def test_build_timeline_multi_sentence_by_token_count():
    text = "I jump. You run fast!"
    # 原文句子 token 数：[2, 3]
    events = [
        _ev("I", 0, 100_000), _ev("jump.", 100_000, 100_000),
        _ev("You", 300_000, 100_000), _ev("run", 450_000, 100_000), _ev("fast!", 600_000, 150_000),
    ]
    tl = core.build_timeline(events, text=text)
    assert [(s["i"], s["j"]) for s in tl["sentences"]] == [(0, 1), (2, 4)]
    assert tl["sentences"][0]["end"] == 20        # 10+10
    assert tl["sentences"][1]["start"] == 30


def test_build_timeline_empty_and_tail_merge():
    assert core.build_timeline([], text="x")["words"] == []
    assert core.build_timeline([], text="x")["sentences"] == []
    # 尾部剩余词并入最后一句（token 数对不上时）
    events = [_ev("a", 0, 100_000), _ev("b", 100_000, 100_000), _ev("c", 200_000, 100_000)]
    tl = core.build_timeline(events, text="a. b.")   # 句子 token 数 [1,1]，第三个词多出来
    assert (tl["sentences"][-1]["i"], tl["sentences"][-1]["j"]) == (1, 2)


def test_timeline_path_and_write(tmp_path):
    mp3 = tmp_path / "话题1-试.mp3"
    p = core.timeline_path(mp3)
    assert p.name == "话题1-试.json"
    out = core.write_timeline(mp3, {"words": [], "sentences": [], "translation": ""})
    assert out == p and p.exists()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd D:\Users\luocj\pyProject\ky\tools && python -m pytest tests/test_text2mp3.py -v`
Expected: FAIL，`AttributeError: module 'tts_core' has no attribute 'split_sentences_text'`

- [ ] **Step 3: 最小实现**

`tts_core.py` 末尾追加：

```python
# ---------- timeline（词级时间轴） ----------

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?…])\s+")


def split_sentences_text(text: str) -> list[str]:
    """按句末标点（. ! ? …）切原文，保留标点；丢弃空白片段。"""
    return [p for p in _SENTENCE_SPLIT.split(text.strip()) if p.strip()]


def _tokens(s: str) -> list[str]:
    """仅保留字母数字撇号，小写——用于把事件词数对到原文句子上。"""
    return re.findall(r"[a-zA-Z0-9']+", s.lower())


def _derive_sentences(words: list[dict], text: str) -> list[dict]:
    n = len(words)
    if n == 0:
        return []
    whole = {"text": text.strip(), "i": 0, "j": n - 1,
             "start": words[0]["s"], "end": words[-1]["s"] + words[-1]["d"]}
    sent_texts = split_sentences_text(text)
    if not sent_texts:
        return [whole]
    out: list[dict] = []
    idx = 0
    for st in sent_texts:
        if idx >= n:
            break
        j = min(idx + max(len(_tokens(st)), 1), n) - 1
        out.append({"text": st, "i": idx, "j": j,
                    "start": words[idx]["s"], "end": words[j]["s"] + words[j]["d"]})
        idx = j + 1
    if idx < n and out:  # 尾部未覆盖的词并入最后一句
        out[-1]["j"] = n - 1
        out[-1]["end"] = words[-1]["s"] + words[-1]["d"]
    return out


def build_timeline(events: list[dict], text: str = "", voice: str = "",
                   rate: str = "+0%", pitch: str = "+0Hz", translation: str = "") -> dict:
    """edge-tts stream 事件（100ns 单位）→ timeline dict（毫秒单位）。纯函数。"""
    words = [{"t": ev["text"], "s": ev["offset"] // 10000, "d": ev["duration"] // 10000}
             for ev in events if ev.get("type") == "WordBoundary"]
    return {"voice": voice, "rate": rate, "pitch": pitch,
            "words": words, "sentences": _derive_sentences(words, text),
            "translation": translation}


def timeline_path(mp3_path: Path) -> Path:
    return mp3_path.with_suffix(".json")


def write_timeline(mp3_path: Path, timeline: dict) -> Path:
    p = timeline_path(mp3_path)
    p.write_text(json.dumps(timeline, ensure_ascii=False), encoding="utf-8")
    return p
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_text2mp3.py -v`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add tools/text2mp3/tts_core.py tests/test_text2mp3.py
git commit -m "feat(text2mp3): timeline 词级时间轴推导与 json 写出"
```

---

### Task 2: 流式合成收集事件（网页 & CLI 出 mp3+json）

**Files:**
- Modify: `tools/text2mp3/tts_core.py`（追加 StreamSink / synthesize）
- Modify: `tools/text2mp3/app.py`（`_synthesize` 与 `/api/tts`）
- Modify: `tools/text2mp3/tts_cli.py`（写 json、打印两个路径）
- Test: `tests/test_text2mp3.py`（追加）

**Interfaces:**
- Consumes: Task 1 的 `build_timeline` / `write_timeline`
- Produces:
  - `class StreamSink` — `__init__(mp3_path: Path)`；`feed(chunk: dict) -> None`；`close() -> None`；属性 `events: list[dict]`
  - `async def synthesize(text: str, voice: str, rate: str, pitch: str, mp3_path: Path, translation: str = "") -> Path` — MP3+json 一起落地，返回 json 路径（app.py 与 tts_cli.py 共用）
  - `/api/tts` 响应新增字段 `json_path: str`

- [ ] **Step 1: 写失败测试**

```python
def test_stream_sink_collects_and_writes(tmp_path):
    mp3 = tmp_path / "a.mp3"
    sink = core.StreamSink(mp3)
    for chunk in [
        {"type": "audio", "data": b"\xff\xf3x"},
        {"type": "WordBoundary", "text": "Hi", "offset": 0, "duration": 100_000},
        {"type": "audio", "data": b"y"},
        {"type": "SentenceBoundary", "offset": 0, "duration": 0, "text": "Hi"},
    ]:
        sink.feed(chunk)
    sink.close()
    assert mp3.read_bytes() == b"\xff\xf3xy"
    assert sink.events == [{"type": "WordBoundary", "text": "Hi", "offset": 0, "duration": 100_000}]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_text2mp3.py -v`
Expected: FAIL，`no attribute 'StreamSink'`

- [ ] **Step 3: 实现**

`tts_core.py` 追加：

```python
class StreamSink:
    """消费 edge-tts stream() 事件流：音频块写文件、收 WordBoundary。纯同步可单测。"""

    def __init__(self, mp3_path: Path):
        self._f = open(mp3_path, "wb")
        self.events: list[dict] = []

    def feed(self, chunk: dict) -> None:
        if chunk.get("type") == "audio":
            self._f.write(chunk["data"])
        elif chunk.get("type") == "WordBoundary":
            self.events.append(chunk)

    def close(self) -> None:
        self._f.close()


async def synthesize(text: str, voice: str, rate: str, pitch: str,
                     mp3_path: Path, translation: str = "") -> Path:
    """edge-tts 合成：MP3 与同名 timeline json 一起落地，返回 json 路径。"""
    import edge_tts  # 延迟导入，保持纯逻辑可单测

    sink = StreamSink(mp3_path)
    try:
        async for chunk in edge_tts.Communicate(text, voice, rate=rate, pitch=pitch).stream():
            sink.feed(chunk)
    finally:
        sink.close()
    return write_timeline(mp3_path, build_timeline(
        sink.events, text=text, voice=voice, rate=rate, pitch=pitch, translation=translation))
```

`app.py`：删除旧 `_synthesize`，`api_tts` 中 `asyncio.run(_synthesize(...))` 一行改为：

```python
    json_path = asyncio.run(core.synthesize(text, voice, rate, pitch, out_path))
```

响应改为：

```python
    return jsonify(ok=True, path=str(out_path), json_path=str(json_path),
                   play=url_for("play", p=str(out_path)))
```

`tts_cli.py`：合成一段改为（替换 `asyncio.run(...)` 与 `print(out)`）：

```python
    json_path = asyncio.run(core.synthesize(
        text, args.voice,
        rate=core.format_rate(args.rate), pitch=core.format_pitch(args.pitch),
        mp3_path=out,
        translation=Path(args.file + ".zh").read_text(encoding="utf-8").strip()
        if Path(args.file + ".zh").is_file() else "",
    ))
    print(out)
    print(json_path)
```

（中文翻译可选：同名 `.txt.zh` 文件存在就写入 timeline。）

- [ ] **Step 4: 跑全部测试确认通过**

Run: `python -m pytest`
Expected: 全部 PASS（26 + 新增）

- [ ] **Step 5: 真实 E2E 探针（联网，手动验证一次事件格式）**

```bash
cd tools/text2mp3
python tts_cli.py C:\Users\luocj\AppData\Local\Temp\claude\topic1_answer.txt -n e2e探针
python -c "import json;d=json.load(open(r'D:\Users\luocj\Obsidian\IELTS\IELTS\学习记录\口语回答\音频\e2e探针.json',encoding='utf-8'));print(len(d['words']),'words',len(d['sentences']),'sentences');print(d['words'][:3]);print(d['sentences'][0])"
rm "D:\Users\luocj\Obsidian\IELTS\IELTS\学习记录\口语回答\音频"/e2e探针.*
```
Expected: words 数 ≈ 280、sentences ≈ 3；words 是毫秒、s/d 为正整数

- [ ] **Step 6: Commit**

```bash
git add tools/text2mp3/tts_core.py tools/text2mp3/app.py tools/text2mp3/tts_cli.py tests/test_text2mp3.py
git commit -m "feat(text2mp3): 合成时流式收集 WordBoundary，MP3+timeline json 双落地"
```

---

### Task 3: speaking-player 骨架（tool.toml + dev_server + manifest 测试）

**Files:**
- Create: `tools/speaking-player/tool.toml`
- Create: `tools/speaking-player/dev_server.py`
- Create: `tools/speaking-player/README.md`（先占位三行，Task 9 补全）
- Test: `tests/test_speaking_player.py`

**Interfaces:**
- Produces:
  - dev_server 提供：`GET /` → index.html；`GET /tracks` 与 `/tracks/` → autoindex json；`/tracks/**` 文件直发；端口 8400（`python dev_server.py [port]`）
  - 面板 slug `speaking-player`（manifest 自动发现）

- [ ] **Step 1: 写失败测试**

`tests/test_speaking_player.py`：

```python
"""speaking-player 骨架：dev_server 纯逻辑 + 面板清单发现。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "tools" / "speaking-player"))
from dev_server import build_autoindex, to_disk  # noqa: E402

BASE = Path(__file__).parents[1] / "tools" / "speaking-player"


def test_build_autoindex_shape(tmp_path):
    (tmp_path / "a.mp3").write_bytes(b"x")
    entries = build_autoindex(tmp_path)
    assert entries == [{"name": "a.mp3", "type": "file",
                        "mtime": entries[0]["mtime"]}]
    assert "GMT" in entries[0]["mtime"]


def test_to_disk_maps_tracks_and_index():
    assert to_disk("/tracks/") == BASE / "fixtures" / "tracks"
    assert to_disk("/tracks") == BASE / "fixtures" / "tracks"
    assert to_disk("/").name == "index.html"


def test_manifest_discovers_speaking_player():
    sys.path.insert(0, str(Path(__file__).parents[1]))
    from launcher.manifest import load_tools

    tools = {t.slug: t for t in load_tools(Path(__file__).parents[1] / "tools")}
    assert tools["speaking-player"].port == 8400
    assert tools["speaking-player"].status == "ready"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_speaking_player.py -v`
Expected: FAIL（模块/文件不存在）

- [ ] **Step 3: 实现骨架**

`tools/speaking-player/tool.toml`：

```toml
name = "口语跟读播放器"
desc = "口语回答 MP3 + 词级时间轴：卡拉OK 逐词高亮、单句循环、倍速、中文翻译（本地预览版）"
category = "英语"
status = "ready"

[run]
cmd = ["python", "dev_server.py"]
port = 8400
url = "http://127.0.0.1:8400"

[links]
live = ""
```

`tools/speaking-player/dev_server.py`（从 audio-player 改造，/tracks/ → fixtures/tracks/）：

```python
"""本地开发服务器：托管静态文件；/tracks/ 返回与 nginx autoindex json 相同格式的列表。

用法：python dev_server.py [port]   # 默认 8400
"""
import json
import mimetypes
import os
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

BASE = Path(__file__).resolve().parent
TRACKS_DIR = BASE / "fixtures" / "tracks"


def _entry(name, full):
    return {
        "name": name,
        "type": "directory" if os.path.isdir(full) else "file",
        "mtime": datetime.fromtimestamp(os.path.getmtime(full), tz=timezone.utc)
        .strftime("%a, %d %b %Y %H:%M:%S GMT"),
    }


def build_autoindex(dirpath):
    """nginx autoindex_format json 同构列表。纯函数，可单测。"""
    return [_entry(n, os.path.join(dirpath, n)) for n in sorted(os.listdir(dirpath))]


def to_disk(url_path):
    """URL -> 磁盘路径：/tracks/** 映射 fixtures/tracks/**。纯函数，可单测。"""
    rel = unquote(url_path).lstrip("/")
    if rel == "tracks" or rel.startswith("tracks/"):
        sub = rel[len("tracks/"):] if rel.startswith("tracks/") else ""
        return TRACKS_DIR / sub
    p = BASE / rel
    return p if p.suffix else BASE / "index.html"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        disk = to_disk(path)
        if path.rstrip("/") == "/tracks" or path.startswith("/tracks/"):
            if disk.is_dir():
                self._send_json(build_autoindex(disk))
                return
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

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))


def main(port=8400):
    print(f"dev server on http://127.0.0.1:{port}/   (tracks -> {TRACKS_DIR})")
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 8400)
```

`README.md` 占位：

```markdown
# 口语跟读播放器（speaking-player）

卡拉OK 式口语跟读页（MP3 + 词级时间轴 json）。开发中，完整说明见 Task 9。
本地预览：`python dev_server.py` → http://127.0.0.1:8400
```

并创建空目录占位 `fixtures/tracks/.gitkeep`。

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_speaking_player.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/speaking-player tests/test_speaking_player.py
git commit -m "feat(speaking-player): 工具骨架 dev_server + 面板清单"
```

---

### Task 4: core.js 纯逻辑 + node 单测

**Files:**
- Create: `tools/speaking-player/core.js`
- Create: `tools/speaking-player/core.test.js`
- Create: `tools/speaking-player/package.json`

**Interfaces:**
- Produces（全部 ESM export，app.js 依赖）:
  - `parseTracks(entries) -> [{file, name, hasSubtitle}]`（只收 .mp3；name 去扩展名；同名 .json 存在则 hasSubtitle）
  - `sortTracks(tracks)`（按文件名自然排序：数字优先）
  - `currentWordIndex(words, tMs) -> number`（二分：s ≤ tMs 的最后一个词下标；无则 -1）
  - `currentSentenceIndex(sentences, tMs) -> number`（同上按 start；无则 -1）
  - `sentenceRange(sentences, idx) -> {start, end}`（越界返回 null）
  - `clampSeek(time, duration)`、`formatTime(sec)`
  - `renderTrackRow(track, index, isCurrent) -> html`、`renderSentence(words, i, j, activeIdx) -> html`（词 span，`data-w` 下标；`w-done`/`w-on` class；文本转义）

- [ ] **Step 1: 写失败测试**

`package.json`：

```json
{
  "name": "speaking-player",
  "private": true,
  "type": "module",
  "scripts": { "test": "node --test" }
}
```

`core.test.js`：

```js
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  parseTracks, sortTracks, currentWordIndex, currentSentenceIndex,
  sentenceRange, clampSeek, formatTime, renderTrackRow, renderSentence,
} from "./core.js";

const WORDS = [
  { t: "To", s: 0, d: 200 }, { t: "me,", s: 240, d: 180 },
  { t: "world.", s: 500, d: 300 },
];

test("parseTracks 配对 json", () => {
  const tracks = parseTracks([
    { name: "话题1.mp3", type: "file" }, { name: "话题1.json", type: "file" },
    { name: "旧.mp3", type: "file" }, { name: "note.txt", type: "file" },
    { name: "子目录", type: "directory" },
  ]);
  assert.deepEqual(tracks, [
    { file: "话题1.mp3", name: "话题1", hasSubtitle: true },
    { file: "旧.mp3", name: "旧", hasSubtitle: false },
  ]);
});

test("sortTracks 数字自然排序", () => {
  const t = (n) => ({ file: n, name: n, hasSubtitle: false });
  assert.deepEqual(
    sortTracks([t("话题10.mp3"), t("话题2.mp3"), t("话题1.mp3")]).map((x) => x.file),
    ["话题1.mp3", "话题2.mp3", "话题10.mp3"],
  );
});

test("currentWordIndex 二分与边界", () => {
  assert.equal(currentWordIndex(WORDS, 0), 0);
  assert.equal(currentWordIndex(WORDS, 300), 1);     // 间隙时停在上一词
  assert.equal(currentWordIndex(WORDS, 799), 2);
  assert.equal(currentWordIndex(WORDS, 800), 2);     // 句尾停最后一词
  assert.equal(currentWordIndex(WORDS, -1), -1);
});

test("currentSentenceIndex / sentenceRange", () => {
  const S = [{ i: 0, j: 1, start: 0, end: 420 }, { i: 2, j: 2, start: 500, end: 800 }];
  assert.equal(currentSentenceIndex(S, 100), 0);
  assert.equal(currentSentenceIndex(S, 600), 1);
  assert.equal(currentSentenceIndex(S, 900), 1);
  assert.deepEqual(sentenceRange(S, 1), { start: 500, end: 800 });
  assert.equal(sentenceRange(S, 9), null);
});

test("clampSeek / formatTime", () => {
  assert.equal(clampSeek(-1, 10), 0);
  assert.equal(clampSeek(11, 10), 10);
  assert.equal(formatTime(83), "1:23");
});

test("renderTrackRow 转义与状态", () => {
  const html = renderTrackRow({ file: "a&b.mp3", name: "a&b", hasSubtitle: true }, 0, true);
  assert.ok(html.includes("a&amp;b"));
  assert.ok(html.includes("is-current"));
  assert.ok(html.includes("data-index=\"0\""));
});

test("renderSentence 高亮 class", () => {
  const html = renderSentence(WORDS, 0, 2, 1);
  assert.ok(html.includes('data-w="1"'));
  assert.ok(html.includes("w-on"));
  assert.ok(html.includes("w-done"));
  assert.ok(!renderSentence(WORDS, 0, 2, -1).includes("w-on"));
});
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd tools/speaking-player && npm test`
Expected: FAIL（Cannot find module './core.js'）

- [ ] **Step 3: 实现 core.js**

```js
// speaking-player/core.js
// 纯逻辑 + 渲染辅助，无副作用（无 DOM / 网络 / <audio>），node:test 单测。

function esc(s) {
  return String(s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

export function parseTracks(entries) {
  if (!Array.isArray(entries)) return [];
  const names = new Set(entries.filter((e) => e && e.type === "file").map((e) => e.name));
  return entries
    .filter((e) => e && e.type === "file" && /\.mp3$/i.test(e.name))
    .map((e) => ({
      file: e.name,
      name: e.name.replace(/\.mp3$/i, ""),
      hasSubtitle: names.has(e.name.replace(/\.mp3$/i, "") + ".json"),
    }));
}

export function sortTracks(tracks) {
  return [...tracks].sort((a, b) => a.file.localeCompare(b.file, "zh-CN",
    { numeric: true, sensitivity: "base" }));
}

export function currentWordIndex(words, tMs) {
  let lo = 0, hi = words.length - 1, ans = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (words[mid].s <= tMs) { ans = mid; lo = mid + 1; } else hi = mid - 1;
  }
  return ans;
}

export function currentSentenceIndex(sentences, tMs) {
  let lo = 0, hi = sentences.length - 1, ans = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (sentences[mid].start <= tMs) { ans = mid; lo = mid + 1; } else hi = mid - 1;
  }
  return ans;
}

export function sentenceRange(sentences, idx) {
  if (!Array.isArray(sentences) || idx < 0 || idx >= sentences.length) return null;
  return { start: sentences[idx].start, end: sentences[idx].end };
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

export function renderTrackRow(track, index, isCurrent) {
  const sub = track.hasSubtitle ? "" : `<span class="no-sub">无字幕</span>`;
  return (
    `<li class="track${isCurrent ? " is-current" : ""}" data-index="${index}" title="${esc(track.file)}">` +
    `<span class="track-name">${esc(track.name)}</span>${sub}</li>`
  );
}

export function renderSentence(words, i, j, activeIdx) {
  let html = "";
  for (let k = i; k <= j; k++) {
    const cls = k < activeIdx ? "w-done" : k === activeIdx ? "w-on" : "";
    html += `<span class="w ${cls}" data-w="${k}">${esc(words[k].t)}</span> `;
  }
  return html;
}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `npm test`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add tools/speaking-player/core.js tools/speaking-player/core.test.js tools/speaking-player/package.json
git commit -m "feat(speaking-player): core.js 纯逻辑（曲目解析/词句定位/渲染）"
```

---

### Task 5: 播放页 UI（index.html + style.css + app.js）

**Files:**
- Create: `tools/speaking-player/index.html`
- Create: `tools/speaking-player/style.css`
- Create: `tools/speaking-player/app.js`

**Interfaces:**
- Consumes: Task 4 的全部导出；Task 3 的 dev_server 路由（`tracks/`、`tracks/<file>`）
- Produces: 完整播放页（列表页 + 跟读页），DOM id 约定见 index.html

- [ ] **Step 1: index.html**

```html
<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>口语跟读</title>
<link rel="stylesheet" href="style.css">
</head>
<body>
  <header>
    <button id="back-btn" hidden>←</button>
    <h1 id="view-title">🎧 口语跟读</h1>
  </header>

  <!-- 曲目列表 -->
  <main id="home-view">
    <ul id="track-list"></ul>
    <p id="home-msg" hidden></p>
  </main>

  <!-- 跟读页 -->
  <main id="player-view" hidden>
    <div id="subtitle-panel">
      <p id="sentence"></p>
      <p id="translation" hidden></p>
      <p id="no-sub-msg" hidden>（无字幕：该曲目没有 timeline json）</p>
    </div>
    <div id="controls">
      <button id="prev-sent" title="上一句">⏮</button>
      <button id="play" title="播放/暂停">▶</button>
      <button id="next-sent" title="下一句">⏭</button>
      <button id="replay-sent" title="单句重播">↺</button>
      <button id="loop-sent" title="单句循环">🔁</button>
      <button id="speed" title="倍速">1x</button>
      <button id="zh" title="中文翻译">译</button>
    </div>
    <div id="progress">
      <span id="cur-time">0:00</span>
      <input type="range" id="seek" min="0" max="1000" value="0">
      <span id="dur-time">0:00</span>
    </div>
    <audio id="audio" preload="metadata"></audio>
  </main>

  <script type="module" src="app.js"></script>
</body>
</html>
```

- [ ] **Step 2: style.css（要点：大字幕、高亮色、手机竖屏优先）**

```css
* { box-sizing: border-box; }
body { margin: 0; font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
       background: #101418; color: #e6edf3; }
header { display: flex; align-items: center; gap: 12px; padding: 14px 16px; }
header h1 { font-size: 18px; margin: 0; flex: 1; }
#back-btn, #controls button { background: #21262d; color: #e6edf3; border: 1px solid #30363d;
       border-radius: 8px; font-size: 18px; padding: 8px 12px; cursor: pointer; }
#track-list { list-style: none; margin: 0; padding: 0 16px; }
.track { padding: 14px 8px; border-bottom: 1px solid #21262d; font-size: 16px; cursor: pointer; }
.track.is-current { color: #58a6ff; }
.no-sub { float: right; font-size: 12px; color: #8b949e; }
#subtitle-panel { min-height: 40vh; display: flex; flex-direction: column;
       justify-content: center; padding: 0 20px; text-align: center; }
#sentence { font-size: clamp(24px, 6vw, 40px); line-height: 1.5; margin: 0; }
#sentence .w { transition: color .15s, opacity .15s; opacity: .45; }
#sentence .w-done { opacity: .8; color: #d6e4ff; }
#sentence .w-on { opacity: 1; color: #ffd66e; }
#translation { font-size: 16px; color: #8b949e; margin: 14px 0 0; }
#no-sub-msg { color: #8b949e; }
#controls { display: flex; justify-content: center; gap: 10px; padding: 12px; flex-wrap: wrap; }
#controls button.active { border-color: #58a6ff; color: #58a6ff; }
#progress { display: flex; align-items: center; gap: 10px; padding: 0 16px 24px; font-size: 13px; }
#seek { flex: 1; }
#home-msg { color: #8b949e; text-align: center; }
```

- [ ] **Step 3: app.js**

```js
// speaking-player/app.js
import {
  parseTracks, sortTracks, currentWordIndex, currentSentenceIndex,
  sentenceRange, clampSeek, formatTime, renderTrackRow, renderSentence,
} from "./core.js";

const TRACKS = "tracks/";
const $ = (id) => document.getElementById(id);
const audio = $("audio");

const state = {
  tracks: [], current: -1,
  timeline: null,          // {words, sentences, translation} | null
  sentIdx: -1, wordIdx: -1,
  loopSent: false, speed: 1, showZh: false,
  zhLoaded: false,
};

/* ---------- 视图 ---------- */
function showHome() {
  $("player-view").hidden = true; $("home-view").hidden = false;
  $("back-btn").hidden = true; $("view-title").textContent = "🎧 口语跟读";
}

async function fetchJson(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error("HTTP " + res.status);
  return res.json();
}

async function loadHome() {
  const msg = $("home-msg"); msg.hidden = true;
  try {
    state.tracks = sortTracks(parseTracks(await fetchJson(TRACKS)));
    $("track-list").innerHTML = state.tracks
      .map((t, i) => renderTrackRow(t, i, i === state.current)).join("");
    if (!state.tracks.length) { msg.textContent = "暂无曲目"; msg.hidden = false; }
  } catch (e) {
    console.error("loadHome failed:", e);
    msg.textContent = "曲目加载失败，请检查服务或 nginx 配置"; msg.hidden = false;
  }
}

/* ---------- 打开曲目 ---------- */
async function playIndex(i) {
  const t = state.tracks[i];
  if (!t) return;
  state.current = i;
  state.timeline = null; state.sentIdx = -1; state.wordIdx = -1;
  $("home-view").hidden = true; $("player-view").hidden = false;
  $("back-btn").hidden = false; $("view-title").textContent = t.name;
  $("no-sub-msg").hidden = true; $("translation").hidden = true;
  $("sentence").textContent = t.name;   // 加载期间先显示曲名
  audio.src = TRACKS + encodeURIComponent(t.file);
  audio.playbackRate = state.speed;
  audio.play().catch(() => {});
  if (t.hasSubtitle) {
    try {
      state.timeline = await fetchJson(TRACKS + encodeURIComponent(t.name + ".json"));
      $("no-sub-msg").hidden = !!state.timeline.words.length;
      updateZh();
    } catch (e) { console.error("timeline 加载失败:", e); $("no-sub-msg").hidden = false; }
  } else {
    $("no-sub-msg").hidden = false;
  }
  loadHome();   // 刷新列表高亮（home 隐藏时安全）
}

/* ---------- 字幕渲染（rAF 驱动） ---------- */
function tick() {
  if (state.timeline && !audio.paused) {
    const tMs = audio.currentTime * 1000;
    const sIdx = currentSentenceIndex(state.timeline.sentences, tMs);
    const range = sentenceRange(state.timeline.sentences, sIdx);
    // 单句循环：句尾前 30ms 回句头
    if (state.loopSent && range && tMs >= range.end - 30) {
      audio.currentTime = range.start / 1000;
      return scheduleTick();
    }
    if (sIdx !== state.sentIdx) {
      state.sentIdx = sIdx; state.wordIdx = -1;
      const s = state.timeline.sentences[sIdx];
      if (s) $("sentence").innerHTML =
        renderSentence(state.timeline.words, s.i, s.j, -1);
    }
    const wIdx = currentWordIndex(state.timeline.words, tMs);
    if (wIdx !== state.wordIdx) {
      state.wordIdx = wIdx;
      const s = state.timeline.sentences[Math.max(sIdx, 0)];
      if (s) $("sentence").innerHTML =
        renderSentence(state.timeline.words, s.i, s.j, wIdx);
    }
  }
  scheduleTick();
}
function scheduleTick() { requestAnimationFrame(tick); }

/* ---------- 控件 ---------- */
function seekSentence(delta) {
  if (!state.timeline) return;
  const idx = clampSentIdx(state.sentIdx + delta);
  const range = sentenceRange(state.timeline.sentences, idx);
  if (range) { audio.currentTime = range.start / 1000; state.sentIdx = -1; }
}
function clampSentIdx(i) {
  const n = state.timeline ? state.timeline.sentences.length : 0;
  return Math.max(0, Math.min(i, n - 1));
}
function updateZh() {
  const show = state.showZh && state.timeline && state.timeline.translation;
  $("translation").hidden = !show;
  if (show) $("translation").textContent = state.timeline.translation;
}

function bind() {
  let scrubbing = false;
  $("back-btn").addEventListener("click", showHome);
  $("track-list").addEventListener("click", (e) => {
    const row = e.target.closest(".track");
    if (row) playIndex(Number(row.dataset.index));
  });
  $("sentence").addEventListener("click", (e) => {
    const w = e.target.closest(".w");
    if (w && state.timeline) {
      const word = state.timeline.words[Number(w.dataset.w)];
      if (word) audio.currentTime = clampSeek(word.s / 1000, audio.duration);
    }
  });
  $("play").addEventListener("click", () => {
    if (audio.paused) audio.play().catch(() => {}); else audio.pause();
  });
  $("prev-sent").addEventListener("click", () => seekSentence(-1));
  $("next-sent").addEventListener("click", () => seekSentence(1));
  $("replay-sent").addEventListener("click", () => seekSentence(0));
  $("loop-sent").addEventListener("click", () => {
    state.loopSent = !state.loopSent;
    $("loop-sent").classList.toggle("active", state.loopSent);
  });
  $("speed").addEventListener("click", () => {
    const SPEEDS = [0.6, 0.8, 1, 1.25];
    state.speed = SPEEDS[(SPEEDS.indexOf(state.speed) + 1) % SPEEDS.length] || 1;
    audio.playbackRate = state.speed;
    $("speed").textContent = state.speed + "x";
  });
  $("zh").addEventListener("click", () => {
    state.showZh = !state.showZh;
    $("zh").classList.toggle("active", state.showZh);
    updateZh();
  });
  $("seek").addEventListener("pointerdown", () => { scrubbing = true; });
  $("seek").addEventListener("pointerup", () => { scrubbing = false; });
  $("seek").addEventListener("input", () => {
    if (audio.duration) audio.currentTime = ($("seek").value / 1000) * audio.duration;
  });
  audio.addEventListener("timeupdate", () => {
    $("cur-time").textContent = formatTime(audio.currentTime);
    if (audio.duration && !scrubbing) $("seek").value = (audio.currentTime / audio.duration) * 1000;
  });
  audio.addEventListener("loadedmetadata", () => {
    $("dur-time").textContent = formatTime(audio.duration);
  });
  audio.addEventListener("play", () => { $("play").textContent = "⏸"; });
  audio.addEventListener("pause", () => { $("play").textContent = "▶"; });
  audio.addEventListener("error", () => { $("sentence").textContent = "⚠ 音频加载失败"; });
}

bind();
showHome();
loadHome();
scheduleTick();
```

- [ ] **Step 4: 手动冒烟（无数据也应不报错）**

```bash
cd tools/speaking-player && python dev_server.py
```
浏览器开 http://127.0.0.1:8400 ：显示「暂无曲目」，控制台无报错。

- [ ] **Step 5: Commit**

```bash
git add tools/speaking-player/index.html tools/speaking-player/style.css tools/speaking-player/app.js
git commit -m "feat(speaking-player): 跟读播放页（大字幕逐词高亮/单句循环/倍速/翻译）"
```

---

### Task 6: fixtures 真实数据 + 本地端到端手动验收

**Files:**
- Create: `tools/speaking-player/fixtures/tracks/话题1-为什么我要学英语.mp3` + `.json`（生成物，**gitignore 掉**）
- Create: `tools/speaking-player/fixtures/tracks/无字幕示例.mp3`（生成物，gitignore）
- Modify: `.gitignore`

- [ ] **Step 1: .gitignore 追加**

```
# speaking-player 本地预览用真实音频（体积大，不入库）
tools/speaking-player/fixtures/tracks/*
!tools/speaking-player/fixtures/tracks/.gitkeep
```

- [ ] **Step 2: 用 tts_cli 生成 fixture（含翻译）**

```bash
cd tools/text2mp3
python tts_cli.py C:\Users\luocj\AppData\Local\Temp\claude\topic1_answer.txt -n 话题1-为什么我要学英语
cp "D:\Users\luocj\Obsidian\IELTS\IELTS\学习记录\口语回答\音频"/话题1-为什么我要学英语.* ../speaking-player/fixtures/tracks/
python tts_cli.py "C:\Users\luocj\AppData\Local\Temp\claude\topic1_answer.txt" -n 无字幕示例
cp "D:\Users\luocj\Obsidian\IELTS\IELTS\学习记录\口语回答\音频\无字幕示例.mp3" ../speaking-player/fixtures/tracks/
rm "D:\Users\luocj\Obsidian\IELTS\IELTS\学习记录\口语回答\音频"/无字幕示例.*
```

- [ ] **Step 3: 手动验收（对照 spec 验收清单 1、2、4 条）**

启动 `python dev_server.py`（8400），浏览器逐项确认：
1. 列表出现两条曲目，「无字幕示例」带「无字幕」标记
2. 点「话题1」：大字幕当前句显示、播放时**逐词高亮跟手**（w-on 金色、已读 w-done 变亮）
3. 点任意词 → 跳到该词；倍速循环切换正常
4. 🔁 单句循环：句尾自动回句头；⏮/⏭/↺ 正常
5. 「无字幕示例」：可播放，显示「无字幕」提示，不报错
6. 手机宽度（DevTools 竖屏）排版正常

- [ ] **Step 4: Commit**

```bash
git add .gitignore
git commit -m "chore(speaking-player): fixtures 音频不入库"
```

---

### Task 7: 一键同步脚本 sync_speaking.py

**Files:**
- Create: `tools/speaking-player/sync_speaking.py`
- Test: `tests/test_speaking_player.py`（追加）

**Interfaces:**
- Produces:
  - `collect_media(src: Path) -> list[Path]`（src 下 *.mp3 与 *.json，按文件名排序；纯函数）
  - `front_files(tool_dir: Path) -> list[Path]`（index.html/app.js/core.js/style.css 存在的；纯函数）
  - `main()`：`--src`（默认读 `../text2mp3/config.json` 的 out_dir）、`--dry-run` 只打印命令
  - 部署目标：`root@47.108.230.162:/www/wwwroot/47.108.230.162/script/speaking/`（`tracks/` + 前端文件），完成后 `chown -R www:www`

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_speaking_player.py`：

```python
def test_collect_media(tmp_path):
    from sync_speaking import collect_media, front_files

    (tmp_path / "a.mp3").write_bytes(b"x")
    (tmp_path / "a.json").write_bytes(b"{}")
    (tmp_path / "b.mp3").write_bytes(b"x")
    (tmp_path / "readme.txt").write_bytes(b"x")
    (tmp_path / "sub").mkdir()
    assert [p.name for p in collect_media(tmp_path)] == ["a.json", "a.mp3", "b.mp3"]

    files = front_files(BASE)
    assert all(f.name in ("index.html", "app.js", "core.js", "style.css") for f in files)
    assert len(files) >= 3
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_speaking_player.py -v`
Expected: FAIL，`No module named 'sync_speaking'`

- [ ] **Step 3: 实现**

```python
"""一键同步：本地口语音频目录 → 服务器 speaking 站点。

用法：
    python sync_speaking.py [--src 目录] [--dry-run]

默认源目录读 ../text2mp3/config.json 的 out_dir；
目标 root@47.108.230.162:/www/wwwroot/47.108.230.162/script/speaking/（tracks/ + 前端4文件）。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parent
REMOTE_HOST = "root@47.108.230.162"
REMOTE_BASE = "/www/wwwroot/47.108.230.162/script/speaking"


def collect_media(src: Path) -> list[Path]:
    """src 下的 .mp3 与 .json（按文件名排序）。"""
    return sorted(p for p in src.iterdir()
                  if p.is_file() and p.suffix.lower() in (".mp3", ".json"))


def front_files(tool_dir: Path) -> list[Path]:
    """要上传的前端静态文件（存在的才算）。"""
    names = ("index.html", "app.js", "core.js", "style.css")
    return [tool_dir / n for n in names if (tool_dir / n).is_file()]


def default_src() -> Path:
    cfg = TOOL_DIR.parent / "text2mp3" / "config.json"
    out = json.loads(cfg.read_text(encoding="utf-8"))["out_dir"] if cfg.is_file() else ""
    return Path(out) if out else Path(r"D:\Users\luocj\Obsidian\IELTS\IELTS\学习记录\口语回答\音频")


def run(cmd: list[str], dry: bool) -> None:
    printable = " ".join(str(c) for c in cmd)
    print("$", printable)
    if not dry:
        subprocess.run(cmd, check=True)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="同步口语音频与前端到服务器")
    ap.add_argument("--src", type=Path, default=default_src(), help="本地音频目录")
    ap.add_argument("--dry-run", action="store_true", help="只打印命令不执行")
    args = ap.parse_args(argv)

    media = collect_media(args.src)
    fronts = front_files(TOOL_DIR)
    if not media:
        sys.exit(f"源目录没有 mp3/json：{args.src}")

    run(["ssh", REMOTE_HOST, f"mkdir -p {REMOTE_BASE}/tracks"], args.dry_run)
    for f in fronts:
        run(["scp", str(f), f"{REMOTE_HOST}:{REMOTE_BASE}/"], args.dry_run)
    if media:
        run(["scp", *[str(p) for p in media], f"{REMOTE_HOST}:{REMOTE_BASE}/tracks/"], args.dry_run)
    run(["ssh", REMOTE_HOST, f"chown -R www:www {REMOTE_BASE}"], args.dry_run)
    print(f"完成：{len(fronts)} 个前端文件 + {len(media)} 个媒体文件")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_speaking_player.py -v`
Expected: PASS

- [ ] **Step 5: dry-run 演练（不碰服务器）**

Run: `python tools/speaking-player/sync_speaking.py --dry-run`
Expected: 打印 mkdir/scp/chown 命令，退出码 0

- [ ] **Step 6: Commit**

```bash
git add tools/speaking-player/sync_speaking.py tests/test_speaking_player.py
git commit -m "feat(speaking-player): 一键同步脚本（音频+json+前端 → 服务器）"
```

---

### Task 8: nginx 配置示例 + 服务器部署（手动，需服务器权限）

**Files:**
- Create: `tools/speaking-player/nginx.conf.example`

- [ ] **Step 1: nginx.conf.example**

```nginx
# ===== 口语跟读播放器 nginx 配置示例 =====
# 服务器实际操作（宝塔）：把下面两个 location 存为
# /www/server/panel/vhost/nginx/extension/47.108.230.162/speaking.conf
# 然后：nginx -t && nginx -s reload

location /script/speaking/ {
    alias /www/wwwroot/47.108.230.162/script/speaking/;
    autoindex off;
}

location /script/speaking/tracks/ {
    alias /www/wwwroot/47.108.230.162/script/speaking/tracks/;
    autoindex on;
    autoindex_format json;
}
```

- [ ] **Step 2: 部署（逐条执行，需要输 ssh 密码）**

```bash
cd tools/speaking-player
scp nginx.conf.example root@47.108.230.162:/www/server/panel/vhost/nginx/extension/47.108.230.162/speaking.conf
ssh root@47.108.230.162 "nginx -t && nginx -s reload"
python sync_speaking.py
```

- [ ] **Step 3: 手机真机验收（对照 spec 验收清单第 3 条）**

手机浏览器开 `http://47.108.230.162/script/speaking/`：列表、逐词高亮、单句循环、倍速、翻译开关全部与本地一致；锁屏后音频继续播（可选，失败不阻塞）。

- [ ] **Step 4: Commit**

```bash
git add tools/speaking-player/nginx.conf.example
git commit -m "docs(speaking-player): nginx 配置示例与部署说明"
```

---

### Task 9: 文档收尾（README + 根 README/summary）

**Files:**
- Modify: `tools/speaking-player/README.md`（占位 → 完整）
- Modify: `README.md`（根，工具表加行）
- Modify: `docs/my-toolkit-summary.md`（工具表加行 + 变更记录）

- [ ] **Step 1: speaking-player/README.md 完整版**

```markdown
# 口语跟读播放器（speaking-player）

卡拉OK 式口语跟读页：MP3 + 同名 timeline json（词级时间轴，由 text2mp3 生成）→
大字幕当前句居中、逐词高亮、点词跳转、单句循环、倍速、中文翻译。纯静态，手机优先。

## 本地预览
cd speaking-player && python dev_server.py    # http://127.0.0.1:8400
真实音频放 fixtures/tracks/（X.mp3 + X.json，gitignore；用 tools/text2mp3/tts_cli.py 生成）

## 测试
node --test                       # core.js 纯逻辑
pytest tests/test_speaking_player.py

## 部署与同步
见 sync_speaking.py（音频+前端一键上服务器）与 nginx.conf.example（一次性配置）。
线上：http://47.108.230.162/script/speaking/

## timeline json 格式
{ "voice","rate","pitch","translation",
  "words":[{"t","s","d"}](ms), "sentences":[{"text","i","j","start","end"}](ms) }
无 json 的 mp3 自动降级为无字幕播放。
```

- [ ] **Step 2: 根 README.md 工具表加一行（表格末尾）**

```markdown
| 口语跟读播放器 | MP3+词级时间轴卡拉OK跟读（本地预览；线上 http://47.108.230.162/script/speaking/ ） | http://127.0.0.1:8400 |
```

（并把 speaking-player 的 `[links] live` 改为该线上地址。）

- [ ] **Step 3: docs/my-toolkit-summary.md**

当前工具表加：

```markdown
| speaking-player | 口语跟读播放器 | 8400 | `python dev_server.py` | MP3+timeline json 卡拉OK逐词高亮跟读；sync_speaking.py 一键上服务器 |
```

变更记录追加：

```markdown
- **2026-08-19**：新增 `speaking-player`（卡拉OK 跟读播放器，:8400）；text2mp3 升级为 MP3+timeline json 双落地。
```

- [ ] **Step 4: 全量回归**

Run: `python -m pytest` + `cd tools/speaking-player && npm test`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add tools/speaking-player/README.md tools/speaking-player/tool.toml README.md docs/my-toolkit-summary.md
git commit -m "docs(speaking-player): README 与工具箱文档收尾"
```

---

## 完成标准（对照 spec 验收清单）

1. ✅ Task 2 Step 5：tts_cli 生成 → mp3+json 同现、结构合法
2. ✅ Task 6 Step 3：本地逐词高亮/点词/循环/倍速/翻译全通过；无字幕曲目降级正常
3. ✅ Task 8 Step 3：手机访问服务器功能一致
4. ✅ Task 6 Step 3 第 5 条：旧 mp3 无 json 可播不报错
