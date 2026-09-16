# 剑桥雅思核心词汇 → 时间轴字幕管线 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把《剑桥雅思核心词汇精讲精练》书后 Recording scripts(OCR 文本)+ 49 个 Track 音频,加工成 subtitle-viewer 可用的双语时间轴字幕 md,上线公网书目网格。

**Architecture:** 新包 `tools/subtitle-viewer/cambridge/`,五段式:extract(OCR→结构化)→ transcribe(Whisper 词级时间)→ align(difflib 词序列对齐)→ translations(JSON 翻译)→ build_md(产出字幕 md)。`run.py` 串流程,中间产物全部 JSON 落盘缓存,可重跑。前端零改动。

**Tech Stack:** Python 3.12 + pypdf(已装)+ faster-whisper(已随 bilibili-subtitles 装好)+ difflib(标准库,**不新增依赖**)。

**Spec:** `docs/superpowers/specs/2026-09-16-subtitles-two-level-nav-and-cambridge-vocab-pipeline-design.md`(需求 B 节)

## Global Constraints

- 源数据路径(含空格/中文,shell 中必须加引号):
  - OCR PDF(全本,已验证):`D:/夸克下载/剑桥雅思核心词汇精讲精练/剑桥雅思核心词汇精讲精练_OCR.pdf`(180 页全文本层;脚本区 163–172 页,共 43 条录音 1a–22b,16/18/21 单元无录音)
  - 源扫描 PDF(补 OCR 用):`D:/夸克下载/剑桥雅思核心词汇精讲精练/剑桥雅思核心词汇精讲精练 (Pdg2Pic, （英）Pauline Cullen编著；何钢译) (z-library.sk, 1lib.sk, z-lib.sk).pdf`(182 页,无文本层)
  - 音频目录:`D:/夸克下载/剑桥雅思核心词汇精讲精练/剑桥雅思核心词汇精讲精练  音频/Track01.mp3 … Track49.mp3`
  - 精翻稿:`D:/夸克下载/剑桥雅思核心词汇精讲精练/录音脚本_Recording1a-2b_中英对照.md`
- 输出 md 目录:`D:/Users/luocj/Ahuaxi/hcrs_devdocs/ielts/剑桥雅思核心词汇精讲精练/`(src_root 下的新书目,中文目录名即书名卡片名)。
- 字幕 md 块格式(与现有完全一致,`TS_RE` 兼容):块间 `---`;`` `M:SS → M:SS` `` 或 `` `H:MM:SS → H:MM:SS` ``;`**英文**` 整行加粗;下一行中文。
- 产出 md 头部含 `<style>`(与 in-use-advanced 现有头部相同)。
- 每个代码任务 TDD:先写 fixture 测试再实现;提交前 `python -m pytest tests/test_cambridge_pipeline.py -q` 全绿。
- 提交信息用 `feat(cambridge):` / `test(cambridge):` 前缀,结尾加 Co-Authored-By 行。

---

### Task 1: OCR 提取与清洗 `extract.py`

**Files:**
- Create: `tools/subtitle-viewer/cambridge/__init__.py`(空文件)
- Create: `tools/subtitle-viewer/cambridge/extract.py`
- Test: `tests/test_cambridge_pipeline.py`

**Interfaces:**
- Produces:
  - `clean_line(s: str) -> str`(OCR 错字清洗)
  - `parse_scripts(pages_text: list[str]) -> list[dict]`,元素 `{"id": "1a", "turns": [{"label": "Speaker A", "text": "..."}]}`;无说话人段落的录音 label 为 `""`
  - `extract_from_pdf(pdf_path: str) -> list[dict]`(pypdf 读页 → `parse_scripts`)

- [ ] **Step 1: 写失败测试**

```python
"""剑桥词汇管线纯逻辑测试。"""
import sys
from pathlib import Path

TOOL = Path(__file__).parents[1] / "tools" / "subtitle-viewer"
sys.path.insert(0, str(TOOL))

PAGES = [
    "Recording 1a\n"
    "Speaker A: On Mondays | often talk about movies.\n"
    "Speaker B: My parents are both teachers.\n",
    "Recording 1b\n"
    "Teacher: Tell me about your family.\n"
    "Student: Well, my immediate family is small!\n"
    "Recording 1c\n"           # 无说话人 → 整段 narration
    "You will hear two people talking about family.\n",
]

def test_clean_line():
    from cambridge.extract import clean_line
    assert clean_line("| often can’t stop") == "I often can't stop"
    assert clean_line("small! and fun") == "small! and fun"   # 紧贴单词的 ! 不是 I
    assert clean_line("abie   able") == "abie able"

def test_parse_scripts():
    from cambridge.extract import parse_scripts
    recs = parse_scripts(PAGES)
    assert [r["id"] for r in recs] == ["1a", "1b", "1c"]
    assert recs[0]["turns"][0] == {"label": "Speaker A",
        "text": "I often talk about movies."}
    assert recs[1]["turns"] == [
        {"label": "Teacher", "text": "Tell me about your family."},
        {"label": "Student", "text": "Well, my immediate family is small!"},
    ]
    assert recs[2]["turns"] == [{"label": "",
        "text": "You will hear two people talking about family."}]
```

- [ ] **Step 2: 跑测试确认失败**

Run:`python -m pytest tests/test_cambridge_pipeline.py -q`
Expected: FAIL,`No module named 'cambridge'`

- [ ] **Step 3: 实现 `cambridge/extract.py`**

```python
"""OCR PDF → Recording 结构化 JSON。文本处理纯函数可单测。"""
from __future__ import annotations

import re
from pathlib import Path

from pypdf import PdfReader

REC_RE = re.compile(r"Recording\s+(\d{1,2}[a-z])\b", re.I)
TURN_RE = re.compile(r"(?:^|\n)\s*([A-Z][A-Za-z .'-]{0,30}):\s")


def clean_line(s: str) -> str:
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = re.sub(r"(?<![A-Za-z])[|!](?![A-Za-z])", "I", s)   # 独立 | / ! → I
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def parse_scripts(pages_text: list[str]) -> list[dict]:
    text = "\n".join(pages_text)
    marks = [(m.start(), m.group(1).lower()) for m in REC_RE.finditer(text)]
    recs = []
    for i, (pos, rid) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        body = text[pos:end]
        nl = body.find("\n")
        body = body[nl + 1:] if nl != -1 else ""
        tm = list(TURN_RE.finditer(body))
        if tm:
            turns = []
            for j, t in enumerate(tm):
                seg_end = tm[j + 1].start() if j + 1 < len(tm) else len(body)
                txt = clean_line(body[t.end():seg_end])
                if txt:
                    turns.append({"label": clean_line(t.group(1)), "text": txt})
        else:
            turns = [{"label": "", "text": clean_line(body)}] if clean_line(body) else []
        if turns:
            recs.append({"id": rid, "turns": turns})
    return recs


def extract_from_pdf(pdf_path: str) -> list[dict]:
    reader = PdfReader(str(pdf_path), strict=False)
    return parse_scripts([(p.extract_text() or "") for p in reader.pages])
```

- [ ] **Step 4: 跑测试确认通过**

Run:`python -m pytest tests/test_cambridge_pipeline.py -q`
Expected: 3 passed

- [ ] **Step 5: 真实数据冒烟 + OCR 覆盖探测**

```bash
PYTHONIOENCODING=utf-8 python -c "
import sys; sys.path.insert(0, 'tools/subtitle-viewer')
from cambridge.extract import extract_from_pdf
recs = extract_from_pdf(r'D:/夸克下载/剑桥雅思核心词汇精讲精练/剑桥雅思核心词汇精讲精练_OCR.pdf')
print('recordings:', len(recs), '| ids:', ' '.join(r['id'] for r in recs))
"
```
预期:43 条,1a–22b,缺 16/18/21(书本身无)。若解析数明显少 → 检查 TURN_RE/REC_RE 对真实文本的适配,修正后重跑(此为提取器调参的验收步)。

- [ ] **Step 6: Commit**

```bash
git add tools/subtitle-viewer/cambridge/__init__.py tools/subtitle-viewer/cambridge/extract.py tests/test_cambridge_pipeline.py
git commit -m "feat(cambridge): OCR 脚本提取与清洗"
```

---

### Task 2: 词级对齐 `align.py`

**Files:**
- Create: `tools/subtitle-viewer/cambridge/align.py`
- Test: `tests/test_cambridge_pipeline.py`(追加)

**Interfaces:**
- Consumes: extract 的 turns `[{label, text}]`。
- Produces:
  - `normalize_word(w: str) -> str`、`words_of(text: str) -> list[str]`
  - `align_turns(turns: list[dict], w_words: list[dict]) -> list[dict]`,在原 dict 上加 `start: float|None, end: float|None, conf: float`(0~1,匹配词占比);无匹配 turn 由邻居插值,conf=0
  - `match_tracks(recordings: list[dict], tracks: dict[str, list[dict]]) -> tuple[dict[str, str], list[str], list[str]]`,返回 `(rec_id→track名 映射, 未匹配录音id, 未匹配track名)`,相似度阈值 0.5;`tracks` 形如 `{"Track01.mp3": [{"w","s","e"}, ...]}`

- [ ] **Step 1: 写失败测试(追加)**

```python
def test_words_of():
    from cambridge.align import words_of
    assert words_of("I can't — STOP!") == ["i", "can't", "stop"]

def test_align_turns_完美匹配与插值():
    from cambridge.align import align_turns
    turns = [
        {"label": "A", "text": "hello world"},
        {"label": "B", "text": "zzz qqq xxx"},          # 完全对不上
        {"label": "C", "text": "good night"},
    ]
    w = [
        {"w": "hello", "s": 1.0, "e": 1.5}, {"w": "world", "s": 1.5, "e": 2.0},
        {"w": "good", "s": 5.0, "e": 5.5}, {"w": "night", "s": 5.5, "e": 6.0},
    ]
    out = align_turns(turns, w)
    assert (out[0]["start"], out[0]["end"]) == (1.0, 2.0)
    assert out[0]["conf"] == 1.0
    assert out[1]["conf"] == 0.0                          # 插值兜底
    assert out[1]["start"] == 2.0 and out[1]["end"] == 5.0
    assert (out[2]["start"], out[2]["end"]) == (5.0, 6.0)

def test_match_tracks():
    from cambridge.align import match_tracks
    recs = [{"id": "1a", "turns": [{"label": "", "text": "on monday school movies"}]}]
    tracks = {
        "Track01.mp3": [{"w": w, "s": i, "e": i + 1} for i, w in
                        enumerate("on monday school movies always".split())],
        "Track02.mp3": [{"w": w, "s": i, "e": i + 1} for i, w in
                        enumerate("totally different words here now".split())],
    }
    m, no_rec, no_track = match_tracks(recs, tracks)
    assert m == {"1a": "Track01.mp3"}
    assert no_track == ["Track02.mp3"]
```

- [ ] **Step 2: 跑测试确认失败**

Run:`python -m pytest tests/test_cambridge_pipeline.py -q`
Expected: 新增 3 条 FAIL(`No module named 'cambridge.align'`)

- [ ] **Step 3: 实现 `cambridge/align.py`**

```python
"""脚本文本 ↔ Whisper 词时间戳 对齐:difflib 词序列匹配,纯逻辑。"""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher


def normalize_word(w: str) -> str:
    w = unicodedata.normalize("NFKC", w).lower().replace("’", "'")
    return re.sub(r"[^a-z0-9']", "", w)


def words_of(text: str) -> list[str]:
    return [x for x in (normalize_word(t) for t in text.split()) if x]


def _sim(a: list[str], b: list[str]) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def align_turns(turns: list[dict], w_words: list[dict]) -> list[dict]:
    script = []                                   # (word, turn_idx)
    for ti, t in enumerate(turns):
        script.extend((w, ti) for w in words_of(t["text"]))
    whisper = [normalize_word(x["w"]) for x in w_words]

    sm = SequenceMatcher(None, [w for w, _ in script], whisper, autojunk=False)
    hit: dict[int, list[dict]] = {ti: [] for ti in range(len(turns))}
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                hit[script[i1 + k][1]].append(w_words[j1 + k])

    need = {ti: sum(1 for _, u in script if u == ti) for ti in hit}
    out = []
    for ti, t in enumerate(turns):
        ws = hit[ti]
        out.append({
            **t,
            "start": min((w["s"] for w in ws), default=None),
            "end": max((w["e"] for w in ws), default=None),
            "conf": round(len(ws) / need[ti], 2) if need[ti] else 0.0,
        })

    dur = w_words[-1]["e"] if w_words else 0.0
    prev_end = 0.0
    for i, o in enumerate(out):
        if o["start"] is None:                    # 无匹配:邻居夹逼插值
            nxt = next((x["start"] for x in out[i + 1:] if x["start"] is not None), dur)
            o.update(start=prev_end, end=nxt, conf=0.0)
        if o["end"] is None or o["end"] <= o["start"]:
            nxt = next((x["start"] for x in out[i + 1:] if x["start"] is not None), dur)
            o["end"] = max(o["start"] + 0.5, min(nxt, dur))
        prev_end = o["end"]
    return out


def match_tracks(recordings: list[dict], tracks: dict[str, list[dict]], threshold: float = 0.5):
    """录音开头词 ↔ 各 Track 开头词的最佳相似配对。"""
    rec_head = {r["id"]: words_of(" ".join(t["text"] for t in r["turns"][:2]))[:40]
                for r in recordings}
    trk_head = {name: [normalize_word(x["w"]) for x in ws][:60]
                for name, ws in tracks.items()}
    mapping, used = {}, set()
    for rid, rwords in sorted(rec_head.items(), key=lambda kv: -len(kv[1])):
        best, best_s = None, threshold
        for name, twords in trk_head.items():
            if name in used:
                continue
            s = _sim(rwords, twords)
            if s > best_s:
                best, best_s = name, s
        if best:
            mapping[rid] = best
            used.add(best)
    no_rec = [rid for rid in rec_head if rid not in mapping]
    no_track = [name for name in trk_head if name not in used]
    return mapping, no_rec, no_track
```

- [ ] **Step 4: 跑测试确认通过**

Run:`python -m pytest tests/test_cambridge_pipeline.py -q`
Expected: 全部 passed

- [ ] **Step 5: Commit**

```bash
git add tools/subtitle-viewer/cambridge/align.py tests/test_cambridge_pipeline.py
git commit -m "feat(cambridge): 词级时间对齐与 Track 配对"
```

---

### Task 3: Whisper 转写(带缓存)`transcribe.py`

**Files:**
- Create: `tools/subtitle-viewer/cambridge/transcribe.py`

**Interfaces:**
- Consumes: 音频目录路径。
- Produces: `transcribe_all(audio_dir: str, cache_dir: str) -> dict[str, list[dict]]`,每个 Track 的词列表 `[{"w": "hello", "s": 1.0, "e": 1.5}]`;结果落盘 `cache_dir/Track01.words.json` 等,重跑直接读缓存。
- I/O 模块,不做单测;由 Task 6 的端到端验证覆盖。

- [ ] **Step 1: 实现**

```python
"""faster-whisper 词级转写,JSON 缓存(依赖已随 bilibili-subtitles 安装)。"""
from __future__ import annotations

import json
from pathlib import Path

_MODEL = None


def _model():
    global _MODEL
    if _MODEL is None:
        from faster_whisper import WhisperModel
        _MODEL = WhisperModel("small.en", device="cpu", compute_type="int8")
    return _MODEL


def transcribe_all(audio_dir: str, cache_dir: str) -> dict[str, list[dict]]:
    audio = sorted(Path(audio_dir).glob("Track*.mp3"))
    if not audio:
        raise SystemExit(f"音频目录没有 Track*.mp3:{audio_dir}")
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    out = {}
    for mp3 in audio:
        cj = cache / (mp3.stem + ".words.json")
        if cj.is_file():
            out[mp3.name] = json.loads(cj.read_text(encoding="utf-8"))
            print(f"[cache] {mp3.name}")
            continue
        print(f"[whisper] {mp3.name} ...")
        segments, _info = _model().transcribe(str(mp3), language="en", word_timestamps=True)
        words = [{"w": w.word.strip(), "s": round(w.start, 2), "e": round(w.end, 2)}
                 for seg in segments for w in (seg.words or [])]
        cj.write_text(json.dumps(words, ensure_ascii=False), encoding="utf-8")
        out[mp3.name] = words
    return out
```

- [ ] **Step 2: 首个 Track 冒烟**

```bash
PYTHONIOENCODING=utf-8 python -c "
import sys; sys.path.insert(0, 'tools/subtitle-viewer')
from cambridge.transcribe import transcribe_all
w = transcribe_all(r'D:/夸克下载/剑桥雅思核心词汇精讲精练/剑桥雅思核心词汇精讲精练  音频', 'tmp/cambridge_cache')
k = sorted(w)[0]
print(k, len(w[k]), '词,首 10:', [x['w'] for x in w[k][:10]])
"
```
预期:几十秒内出词表,首词与 Track 内容相符。(全套 49 条耗时较长,本步只验证可跑;全部转写在 Task 6 批量执行。)

- [ ] **Step 3: Commit**

```bash
git add tools/subtitle-viewer/cambridge/transcribe.py
git commit -m "feat(cambridge): faster-whisper 词级转写与 JSON 缓存"
```

---

### Task 4: 生成字幕 md `build_md.py`

**Files:**
- Create: `tools/subtitle-viewer/cambridge/build_md.py`
- Test: `tests/test_cambridge_pipeline.py`(追加)

**Interfaces:**
- Consumes: Task 2 的带时间 turns;翻译 dict `{turn_index: 中文}`;Unit 名。
- Produces:
  - `fmt_ts(sec: float) -> str`(`"1:23"` / `"1:02:03"`)
  - `build_md(rec_id: str, unit: str, turns: list[dict], track_name: str, zh: dict[int, str]) -> str`(完整字幕 md 文本)
  - md 文件名:`f"Recording {rec_id}｜Unit {unit}.md"`(rec_id 如 `1a`,unit 如 `1 Family`)

- [ ] **Step 1: 写失败测试(追加)**

```python
def test_fmt_ts():
    from cambridge.build_md import fmt_ts
    assert fmt_ts(83.4) == "1:23"
    assert fmt_ts(3723) == "1:02:03"

def test_build_md_格式与时间戳():
    from cambridge.build_md import build_md
    from subtitle_lib import has_timestamps
    turns = [
        {"label": "Speaker A", "text": "Hello world.", "start": 0.0, "end": 2.0, "conf": 1.0},
        {"label": "Speaker B", "text": "Good night.", "start": 5.0, "end": 6.0, "conf": 1.0},
    ]
    md = build_md("1a", "1 Family", turns, "Track01.mp3", {0: "你好,世界。", 1: "晚安。"})
    assert has_timestamps(md)
    assert "`0:00 → 0:05`" in md          # 块结束=下一块起点
    assert "`0:05 → 0:06`" in md
    assert "**Speaker A: Hello world.**" in md
    assert "你好,世界。" in md
    assert "Track01.mp3" in md
```

- [ ] **Step 2: 跑测试确认失败**

Run:`python -m pytest tests/test_cambridge_pipeline.py -q`
Expected: 新增 2 条 FAIL

- [ ] **Step 3: 实现 `cambridge/build_md.py`**

```python
"""带时间 turns + 翻译 → subtitle-viewer 字幕 md。"""
from __future__ import annotations

STYLE = ("<style>\n  p { font-size: 18px; }\n"
         "  p > strong:only-child { font-size: 28px; }\n"
         "  p > code:only-child { font-size: 16px; }\n"
         "  blockquote p { font-size: inherit; }\n</style>")


def fmt_ts(sec: float) -> str:
    sec = max(0, int(sec))
    m, s = divmod(sec, 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def build_md(rec_id: str, unit: str, turns: list[dict], track_name: str,
             zh: dict[int, str]) -> str:
    head = (
        f"# 剑桥雅思核心词汇精讲精练 Recording {rec_id}｜Unit {unit}\n\n"
        f"> 来源:剑桥雅思核心词汇精讲精练(Pauline Cullen)书后 Recording scripts · 音频 {track_name}\n"
        f"> 时间轴:`faster-whisper small.en 词级对齐` · 中文 `精翻` · 共 {len(turns)} 条\n\n"
        f"{STYLE}\n"
    )
    parts = []
    for i, t in enumerate(turns):
        end = turns[i + 1]["start"] if i + 1 < len(turns) else (t["end"] or t["start"] + 5)
        end = max(end, t["start"] + 0.5)
        en = f"{t['label']}: {t['text']}" if t["label"] else t["text"]
        block = f"`{fmt_ts(t['start'])} → {fmt_ts(end)}`\n\n**{en}**"
        z = zh.get(i, "")
        if z:
            block += f"\n\n{z}"
        parts.append(f"---\n\n{block}")
    return head + "\n" + "\n\n".join(parts) + "\n"
```

- [ ] **Step 4: 跑测试确认通过**

Run:`python -m pytest tests/test_cambridge_pipeline.py -q`
Expected: 全部 passed

- [ ] **Step 5: Commit**

```bash
git add tools/subtitle-viewer/cambridge/build_md.py tests/test_cambridge_pipeline.py
git commit -m "feat(cambridge): 字幕 md 生成器"
```

---

### Task 5: 编排 `run.py` + 全量转写 + 映射报告

**Files:**
- Create: `tools/subtitle-viewer/cambridge/run.py`
- Create: `tools/subtitle-viewer/cambridge/units.json`(25 个 Unit 标题,内容执行时从书目录页/公开 TOC 填,`{"1": "Family", "2": "Childhood & Memory", ...}`;Unit 1/2 以精翻稿为准)
- Create: `tools/subtitle-viewer/cambridge/translations/`(目录,`1a.json` 等,内容 Task 6/7 提供;缺失时中文留空也能出稿)

**Interfaces:**
- Consumes: 前四个任务的全部产物。
- Produces: `python -m cambridge.run [--only 1a] [--out 目录] [--dry]`——extract→transcribe→match→align→build 全流程;中间产物在 `tmp/cambridge_cache/`(`recordings.json`、`*.words.json`、`match.json`);`--dry` 只出映射/覆盖报告不写 md。

- [ ] **Step 1: 实现 `cambridge/run.py`**

```python
"""剑桥雅思核心词汇 → 字幕 md 全流程。中间产物缓存于 tmp/cambridge_cache。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))          # tools/subtitle-viewer → import cambridge.*

from cambridge.align import align_turns, match_tracks
from cambridge.build_md import build_md
from cambridge.extract import extract_from_pdf
from cambridge.transcribe import transcribe_all

OCR_PDF = r"D:/夸克下载/剑桥雅思核心词汇精讲精练/剑桥雅思核心词汇精讲精练_OCR.pdf"
AUDIO_DIR = r"D:/夸克下载/剑桥雅思核心词汇精讲精练/剑桥雅思核心词汇精讲精练  音频"
CACHE = HERE.parents[2] / "tmp" / "cambridge_cache"
DEFAULT_OUT = Path(r"D:/Users/luocj/Ahuaxi/hcrs_devdocs/ielts/剑桥雅思核心词汇精讲精练")


def load_json(path: Path, producer):
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    data = producer()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return data


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="只处理指定录音,如 1a")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--dry", action="store_true", help="只出报告,不写 md")
    args = ap.parse_args()

    recs = load_json(CACHE / "recordings.json", lambda: extract_from_pdf(OCR_PDF))
    tracks = transcribe_all(AUDIO_DIR, CACHE)
    mapping, no_rec, no_track = match_tracks(recs, tracks)
    (CACHE / "match.json").write_text(
        json.dumps({"mapping": mapping, "no_rec": no_rec, "no_track": no_track},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    units = json.loads((HERE / "units.json").read_text(encoding="utf-8"))

    report = []
    for rec in recs:
        if args.only and rec["id"] != args.only:
            continue
        rid = rec["id"]
        if rid not in mapping:
            report.append(f"SKIP {rid}: 无匹配 Track"); continue
        aligned = align_turns(rec["turns"], tracks[mapping[rid]])
        tfile = HERE / "translations" / f"{rid}.json"
        zh = ({int(k): v for k, v in json.loads(tfile.read_text(encoding="utf-8")).items()}
              if tfile.is_file() else {})
        unit = f"{rid.rstrip('abcdefghijklmnopqrstuvwxyz')} {units.get(rid.rstrip('abcdefghijklmnopqrstuvwxyz'), '')}".strip()
        low = sum(1 for t in aligned if t["conf"] < 0.5)
        report.append(f"{rid} → {mapping[rid]}: {len(aligned)} 段, 低置信 {low}, 中文 {len(zh)}/{len(aligned)}")
        if args.dry:
            continue
        md = build_md(rid, unit, aligned, mapping[rid], zh)
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / f"Recording {rid}｜Unit {unit}.md").write_text(md, encoding="utf-8")

    print("\n".join(report) or "无录音")
    print("未匹配录音:", " ".join(no_rec) or "-", "| 未匹配 Track:", " ".join(no_track) or "-")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 首跑 dry 报告(触发全量转写,耗时)**

```bash
cd tools/subtitle-viewer && PYTHONIOENCODING=utf-8 python -m cambridge.run --dry
```
预期:49 条 Track 转写缓存落地;报告列出每条录音的映射与置信度。**人工检查**:`no_rec`/`no_track` 是否合理(前奏/无人声 Track 允许剩余)、低置信录音清单。映射可疑 → 记录并核对(听音频首句 vs 脚本首句)。

- [ ] **Step 3: units.json 填充并提交**

从书目录(公开 TOC,Pauline Cullen《Cambridge Vocabulary for IELTS》)填 25 个 Unit 标题;Unit 1 `Family`、Unit 2 `Childhood & Memory` 以精翻稿为准。

- [ ] **Step 4: Commit**

```bash
git add tools/subtitle-viewer/cambridge/run.py tools/subtitle-viewer/cambridge/units.json
git commit -m "feat(cambridge): 全流程编排与映射报告"
```

---

### Task 6: 精翻稿 1a–2b 转换 + 端到端验收 Recording 1a

**Files:**
- Create: `tools/subtitle-viewer/cambridge/translations/1a.json` … `2b.json`(5 个文件)

**Interfaces:**
- Produces: 每个 JSON 形如 `{"0": "中文…", "1": "中文…"}`,键 = turn 序号,与 extract 的 turn 顺序一致。

- [ ] **Step 1: 人工转换精翻稿**

对照 `录音脚本_Recording1a-2b_中英对照.md` 与 `tmp/cambridge_cache/recordings.json` 中 1a–2b 的 turns 顺序,把每段中文写成 translations JSON(由执行者完成,非代码)。1a 的 narration 前言若 OCR 中无对应 turn 则跳过。

- [ ] **Step 2: 端到端产出 1a**

```bash
cd tools/subtitle-viewer && PYTHONIOENCODING=utf-8 python -m cambridge.run --only 1a --out tmp/cambridge_out
PYTHONIOENCODING=utf-8 head -40 "tmp/cambridge_out/Recording 1a｜Unit 1 Family.md"
```
预期:时间戳单调递增、块内英文与精翻稿一致、中文对位。

- [ ] **Step 3: 本地验收**

```bash
python tools/subtitle-viewer/dev_server.py &     # 8800
# 浏览器 http://127.0.0.1:8800 → 列表出现 tmp 输出(或复制 1a md 到 src_root/剑桥雅思核心词汇精讲精练/ 后刷新)
```
用户按实际音频试听跟读 1a,确认滚动/高亮与音频基本对齐(±2s 内可接受,±1s 可微调)。**不通过 → 回到对齐参数/映射排查,禁止带病推进。**

- [ ] **Step 4: Commit**

```bash
git add tools/subtitle-viewer/cambridge/translations/
git commit -m "feat(cambridge): 1a-2b 精翻转换"
```

---

### Task 7: 剩余录音翻译(内容任务)+ 批量产出 + 上线

**Files:**
- Create: `tools/subtitle-viewer/cambridge/translations/` 其余全部 `*.json`(执行者依 recordings.json 逐段翻译,保留说话人语气,术语与 1a–2b 精翻稿风格一致)

- [ ] **Step 1: 批量翻译**

对 3a 起每条录音的每个 turn 写中文(dry 报告里低置信录音同样翻译,时间轴走兜底)。分批提交(每 ~10 条一个 commit,`feat(cambridge): 翻译 3a-6c` 式)。

- [ ] **Step 2: 批量生成**

```bash
cd tools/subtitle-viewer && PYTHONIOENCODING=utf-8 python -m cambridge.run
```
预期:全部录音 md 写入 `src_root/剑桥雅思核心词汇精讲精练/`;报告低置信清单留档。

- [ ] **Step 3: 同步公网 + 验收**

```bash
cd tools/subtitle-viewer && python sync_subtitles.py
curl -s http://47.108.230.162/script/subtitles/manifest.json | python -c "import json,sys; d=json.load(sys.stdin)['docs']; print(len(d)); print([x['path'] for x in d if '剑桥' in x['path']][:3])"
```
浏览器公网验收:书目网格出现「剑桥雅思核心词汇精讲精练」卡片 → 点进网格 → 1a 跟读与 Task 6 验收一致。

- [ ] **Step 4: README + 收尾提交**

`tools/subtitle-viewer/README.md` 补一节「剑桥雅思词汇管线」:`python -m cambridge.run` 用法、缓存位置、翻译文件约定。

```bash
git add tools/subtitle-viewer/README.md tools/subtitle-viewer/cambridge/translations/
git commit -m "feat(cambridge): 全量字幕上线"
```
