# 词汇复习工具(vocab-review)实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把公网字幕库(60 篇双语 md)构建成个人词池,公网静态页 + SM-2 间隔复习,手机优先。

**Architecture:** 电脑端 `build.py` 扫 md + 查 ECDICT 生成 `vocab.json`;`web/` 静态三件套(SM-2 纯逻辑在 core.js,node --test 可测)部署到 `/script/vocab/`;进度存手机 localStorage,导出/导入 JSON 备份。无后端。

**Tech Stack:** Python 3 标准库(csv/json/argparse)+ 原生 JS(ESM)+ node --test + scp/ssh 部署。

**Spec:** `docs/superpowers/specs/2026-09-28-vocab-review-design.md`(决策与规则以 spec 为准)

## Global Constraints

- 纯标准库,不加 pip 依赖(ECDICT 解压若需 7z 允许临时 `pip install py7zr`)
- ECDICT 词级标签:`zk`=中考 `gk`=高考 `cet4/cet6/ky/toefl/ielts/gre`;默认划线 `gk`(zk+gk=已会)
- SM-2:认识 r+1,i=1→3→round(i×e),r≥4 或 i≥21 毕业;不认识 e−0.2(下限 1.3),due=+10min
- localStorage key:`vocab-review-state-v1`;词以**词形原形(lemma)**为键
- UI 配色浅底紫(与字幕站一致),390px 手机优先;文案全中文
- 每任务 TDD:先写失败测试再实现;提交信息带 Co-Authored-By

---

### Task 1: ECDICT 加载器 `ecdict.py`

**Files:**
- Create: `tools/vocab-review/ecdict.py`
- Test: `tests/test_vocab_review.py`(本工具全部 pytest 集中此文件)

**Interfaces:**
- Produces: `load_for_tokens(csv_path: Path, tokens: set[str]) -> tuple[dict[str, dict], dict[str, str]]`
  返回 (entries, lemmas):entries[token] = `{word, phon, translation, tag, frq, exchange}`(无收录则无该键);
  lemmas[token] = 词形原形(token 本身或 exchange 的 `0:`/`1:` 指向,解析不到原形时为 token 自身)
- CSV 字段名(ECDICT stardict.csv 表头):`word,phon,translation,exchange,frq,tag,...`(frq 为 COCA 词频排名,0=未收录语料)

- [ ] **Step 0: 下载 ECDICT 数据(一次性环境准备)**

从 https://github.com/skywind3000/ecdict 的 Releases 下载 csv 压缩包(约 54MB,7z 格式),
解压出 `stardict.csv`(约 190MB)放到 `tmp/ecdict/stardict.csv`。Windows 无 7z 命令时:

```bash
python -m pip install py7zr
python -c "import py7zr; py7zr.SevenZipFile(r'<下载的7z路径>').extractall(r'tmp/ecdict')"
```

验证:`tmp/ecdict/stardict.csv` 存在且 >100MB,表头含 `exchange`。

- [ ] **Step 1: 写失败测试**

```python
"""vocab-review 构建纯逻辑测试。"""
import sys
from pathlib import Path

TOOL = Path(__file__).parents[1] / "tools" / "vocab-review"
sys.path.insert(0, str(TOOL))


def _mini_csv(tmp_path):
    rows = [
        "word,phon,translation,exchange,frq,tag",
        "run,/rʌn/,v. 跑,i:running/3:runs/d:ran/p:run,100,zk gk",
        "running,/ˈrʌnɪŋ/,n. 跑步,0:run,2000,gk",
        "reclaim,/rɪˈkleɪm/,vt. 开拓；回收利用,,8000,cet6 ky ielts",
    ]
    p = tmp_path / "mini.csv"
    p.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return p


def test_load_for_tokens_resolves_lemma_and_fields(tmp_path):
    import ecdict
    entries, lemmas = ecdict.load_for_tokens(_mini_csv(tmp_path), {"running", "ran", "reclaim", "zzz"})
    assert lemmas["running"] == "run"          # exchange 0:run → 原形
    assert lemmas["ran"] == "ran"              # 无独立词条 → 保持自身
    assert entries["reclaim"]["tag"] == "cet6 ky ielts"
    assert entries["reclaim"]["translation"].startswith("vt.")
    assert "zzz" not in entries and "zzz" not in lemmas
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_vocab_review.py -q`
Expected: FAIL `ModuleNotFoundError: No module named 'ecdict'`

- [ ] **Step 3: 实现**

```python
"""ECDICT stardict.csv 只读访问:为给定 token 集合取词条并解析词形原形。"""
from __future__ import annotations

import csv
import re
from pathlib import Path

_FIELDS = ("word", "phon", "translation", "exchange", "frq", "tag")
_EX_LINK = re.compile(r"(?:^|/)([01]):([^/]+)")


def _lemma_of(exchange: str, word: str) -> str:
    """exchange 的 0:/1: 段指向原形;解析不到返回自身。"""
    for m in _EX_LINK.finditer(exchange or ""):
        return m.group(2)
    return word


def load_for_tokens(csv_path: Path, tokens: set[str]) -> tuple[dict[str, dict], dict[str, str]]:
    wanted = {t.lower() for t in tokens}
    entries: dict[str, dict] = {}
    lemmas: dict[str, str] = {}
    with open(csv_path, encoding="utf-8", errors="ignore", newline="") as f:
        for row in csv.DictReader(f):
            word = (row.get("word") or "").strip().lower()
            if word not in wanted or word in entries:
                continue
            entries[word] = {k: (row.get(k) or "").strip() for k in _FIELDS}
            entries[word]["frq"] = int(entries[word]["frq"] or 0)
    for token in wanted:
        entry = entries.get(token)
        lemmas[token] = _lemma_of(entry["exchange"], token) if entry else token
    # 原形若本身无词条但变体有:把变体词条挂给查询方使用即可(保持 entries 键不变)
    return entries, lemmas
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_vocab_review.py -q` → PASS

- [ ] **Step 5: Commit**

```bash
git add tools/vocab-review/ecdict.py tests/test_vocab_review.py
git commit -m "feat(vocab-review): ECDICT 加载器——词条抽取与词形原形解析"
```

---

### Task 2: md 收词与分句 `build.py`(基础函数)

**Files:**
- Create: `tools/vocab-review/build.py`
- Test: `tests/test_vocab_review.py`(追加)

**Interfaces:**
- Produces:
  - `md_english_lines(md_text: str) -> list[str]`(取 `**...**` 行内部)
  - `doc_title(md_text: str) -> str`(首个 `# ` 标题,无则 `"未命名"`)
  - `tokenize(text: str) -> list[str]`(小写纯字母词,长度≥2)
  - `split_sentences(lines: list[str]) -> list[str]`(句号/问号/叹号切句,保留 4-30 词)

- [ ] **Step 1: 写失败测试(追加到 tests/test_vocab_review.py)**

```python
MD = """# 测试书 Unit 1｜示例

> 来源: xxx

---

`0:00:01 → 0:00:05`

**Reclamation of old land takes years. And they Running fast!**

---

`0:00:05 → 0:00:08`

**Do you know the word reclaim?**
"""


def test_md_english_lines_and_title():
    import build
    lines = build.md_english_lines(MD)
    assert lines == ["Reclamation of old land takes years. And they Running fast!",
                     "Do you know the word reclaim?"]
    assert build.doc_title(MD) == "测试书 Unit 1｜示例"


def test_tokenize_keeps_alpha_words_only():
    import build
    assert build.tokenize("Reclamation of OLD land, takes 3 years--OK? A I") == \
        ["reclamation", "of", "old", "land", "takes", "years", "ok"]


def test_split_sentences_filters_by_word_count():
    import build
    sents = build.split_sentences(["Reclamation takes years. Yes! Do you know it?"])
    assert sents == ["Reclamation takes years.", "Do you know it?"]  # Yes! 仅1词被滤
```

- [ ] **Step 2: 跑测试确认失败** → `python -m pytest tests/test_vocab_review.py -q` FAIL(No module build)

- [ ] **Step 3: 实现**

```python
"""vocab-review 词池构建:字幕 md → 划线生词 + 例句 → vocab.json。用法:

    python build.py [--src 目录] [--ecdict csv] [--out web/vocab.json] [--level gk]
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parent
_BOLD_LINE = re.compile(r"^\*\*(.+)\*\*$")
_TOKEN = re.compile(r"[a-z]{2,}")
_SENT_SPLIT = re.compile(r"(?<=[.?!])\s+")


def md_english_lines(md_text: str) -> list[str]:
    out = []
    for line in md_text.splitlines():
        m = _BOLD_LINE.match(line.strip())
        if m:
            out.append(m.group(1).strip())
    return out


def doc_title(md_text: str) -> str:
    for line in md_text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return "未命名"


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def split_sentences(lines: list[str]) -> list[str]:
    out = []
    for line in lines:
        for sent in _SENT_SPLIT.split(line):
            sent = sent.strip()
            if 4 <= len(sent.split()) <= 30:
                out.append(sent)
    return out
```

- [ ] **Step 4: 跑测试确认通过**
- [ ] **Step 5: Commit** `git commit -m "feat(vocab-review): md 收词与分句基础函数"`

---

### Task 3: 划线分类与例句选择

**Files:**
- Modify: `tools/vocab-review/build.py`(追加)
- Test: `tests/test_vocab_review.py`(追加)

**Interfaces:**
- Consumes: Task 1 的 entry 结构 `{tag, frq}`、Task 2 的句子函数
- Produces:
  - `classify(entry: dict | None, level: str = "gk") -> str` → `"known"|"candidate"|"drop"`
  - `KNOWN_TIERS = ["zk", "gk"]`、`CANDIDATE_TIERS = ["cet4", "cet6", "ky", "toefl", "ielts", "gre"]`
  - `pick_sentences(variants: set[str], sentences: list[tuple[str, str]], limit: int = 2) -> list[dict]`
    (sentences 元素 = (句子, 来源标题);返回 `[{en, from}]`,按词数升序取前 limit)

- [ ] **Step 1: 写失败测试(追加)**

```python
def test_classify_by_tags_and_frequency():
    import build
    gk = {"tag": "zk gk", "frq": 300}
    cet6 = {"tag": "cet6 ky ielts", "frq": 8000}
    plain_high = {"tag": "", "frq": 1500}       # 无标签但词频前5000
    plain_low = {"tag": "", "frq": 0}           # 未收录语料 → 丢弃
    assert build.classify(gk) == "known"
    assert build.classify(cet6) == "candidate"
    assert build.classify(plain_high) == "known"
    assert build.classify(plain_low) == "drop"
    assert build.classify(None) == "drop"


def test_pick_sentences_shortest_first_with_source():
    import build
    sents = [("Reclamation of land takes years and costs money.", "书A Unit 1"),
             ("They reclaim it.", "书B Unit 2"),
             ("We can reclaim the plastics from old computers now.", "书B Unit 2")]
    picked = build.pick_sentences({"reclaim", "reclamation"}, sents)
    assert len(picked) == 2
    assert picked[0]["en"] == "We can reclaim the plastics from old computers now."
    assert picked[0]["from"] == "书B Unit 2"
```

- [ ] **Step 2: 跑测试确认失败**

- [ ] **Step 3: 实现(追加到 build.py)**

```python
KNOWN_TIERS = ["zk", "gk"]
CANDIDATE_TIERS = ["cet4", "cet6", "ky", "toefl", "ielts", "gre"]
FREQ_KNOWN_RANK = 5000      # 无标签但 COCA 排名前 5000 视为常用已会


def classify(entry: dict | None, level: str = "gk") -> str:
    """按 ECDICT 标签/词频划线;level 可上调(如 cet4)扩大已会范围。"""
    if not entry:
        return "drop"
    tags = set((entry["tag"] or "").split())
    known_tiers = KNOWN_TIERS[:KNOWN_TIERS.index(level) + 1] if level in KNOWN_TIERS else KNOWN_TIERS
    if tags & set(known_tiers):
        return "known"
    if tags & set(CANDIDATE_TIERS):
        return "candidate"
    if 0 < entry["frq"] <= FREQ_KNOWN_RANK:
        return "known"
    return "candidate"


def pick_sentences(variants: set[str], sentences: list[tuple[str, str]], limit: int = 2) -> list[dict]:
    hits = [(len(en.split()), en, src) for en, src in sentences
            if variants & set(tokenize(en))]
    hits.sort()
    return [{"en": en, "from": src} for _, en, src in hits[:limit]]
```

- [ ] **Step 4: 跑测试确认通过**
- [ ] **Step 5: Commit** `git commit -m "feat(vocab-review): 词级划线与例句选择"`

---

### Task 4: 构建主管线 `build()` + CLI(真数据出 vocab.json)

**Files:**
- Modify: `tools/vocab-review/build.py`(追加)
- Test: `tests/test_vocab_review.py`(追加,mini 数据集成)

**Interfaces:**
- Consumes: ecdict.load_for_tokens、Task 2/3 全部函数
- Produces: `build(src_root: Path, ecdict_path: Path, level: str = "gk") -> dict`
  返回 `{"version": 1, "generated_at": "...", "words": [...], "stats": {...}}`;
  words 元素 `{w, phon, def, tags, sents: [{en, from}]}`;stats `{total, known, candidate, dropped}`
- CLI:`--src`(默认读 subtitle-viewer config.json 的 src_root)`--ecdict`(默认 `tmp/ecdict/stardict.csv`)`--out`(默认 `web/vocab.json`)`--level`(默认 gk)

- [ ] **Step 1: 写失败测试(追加;mini ecdict + mini md 集成)**

```python
def test_build_end_to_end_with_fixtures(tmp_path):
    import build, ecdict
    src = tmp_path / "docs"; src.mkdir()
    (src / "a.md").write_text(
        "# 书A Unit 1\n\n---\n\n`0:00:01 → 0:00:05`\n\n"
        "**They reclaim the land quickly. Running helps.**\n\n---\n", encoding="utf-8")
    result = build.build(src, _mini_csv(tmp_path), level="gk")
    words = {w["w"]: w for w in result["words"]}
    assert "reclaim" in words and words["reclaim"]["def"].startswith("vt.")
    assert words["reclaim"]["sents"][0]["en"] == "They reclaim the land quickly."
    assert words["reclaim"]["tags"] == "cet6 ky ielts"
    assert "run" not in words                      # zk/gk → 已会,不进 words
    assert result["stats"]["total"] >= 4
```

- [ ] **Step 2: 跑测试确认失败**

- [ ] **Step 3: 实现(追加到 build.py)**

```python
def build(src_root: Path, ecdict_path: Path, level: str = "gk") -> dict:
    import datetime
    import ecdict as ecdict_mod

    docs = sorted(p for p in src_root.rglob("*.md") if "`" in p.read_text(encoding="utf-8")[:400])
    sentences: list[tuple[str, str]] = []      # (句子, 来源)
    token_case: dict[str, list[bool]] = {}     # token -> 是否首字母大写(专名判定)
    counts: dict[str, int] = {}
    for path in docs:
        text = path.read_text(encoding="utf-8")
        title = doc_title(text)
        lines = md_english_lines(text)
        sentences.extend((s, title) for s in split_sentences(lines))
        for line in lines:
            for raw in re.findall(r"[A-Za-z]{2,}", line):
                low = raw.lower()
                counts[low] = counts.get(low, 0) + 1
                token_case.setdefault(low, []).append(raw[0].isupper())

    entries, lemmas = ecdict_mod.load_for_tokens(ecdict_path, set(counts))

    stats = {"total": 0, "known": 0, "candidate": 0, "dropped": 0}
    lemma_counts: dict[str, int] = {}
    lemma_variants: dict[str, set[str]] = {}
    for token, n in counts.items():
        always_cap = all(token_case[token]) and counts[token] >= 2
        stats["total"] += 1 if lemmas[token] not in lemma_counts else 0
        lemma_counts[lemmas[token]] = lemma_counts.get(lemmas[token], 0) + n
        lemma_variants.setdefault(lemmas[token], set()).add(token)

    words = []
    for lemma in sorted(lemma_counts, key=lambda w: -lemma_counts[w]):
        entry = entries.get(lemma) or entries.get(next(iter(lemma_variants[lemma])))
        kind = classify(entry, level)
        if kind == "drop" or (entry is None and lemma_counts[lemma] < 2):
            stats["dropped"] += 1
            continue
        stats[kind] += 1
        if kind == "candidate":
            words.append({
                "w": lemma,
                "phon": entry.get("phon", "") if entry else "",
                "def": (entry.get("translation", "") if entry else "").replace("\n", "; "),
                "tags": entry.get("tag", "") if entry else "",
                "sents": pick_sentences(lemma_variants[lemma] | {lemma}, sentences),
            })
    stats["total"] = len(lemma_counts)
    return {
        "version": 1,
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "words": words, "stats": stats,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="字幕库 → vocab.json 词池")
    ap.add_argument("--src", type=Path, default=None)
    ap.add_argument("--ecdict", type=Path, default=TOOL_DIR.parents[2] / "tmp" / "ecdict" / "stardict.csv")
    ap.add_argument("--out", type=Path, default=TOOL_DIR / "web" / "vocab.json")
    ap.add_argument("--level", default="gk", choices=["zk", "gk", "cet4"])
    args = ap.parse_args()
    src = args.src
    if src is None:
        cfg = json.loads((TOOL_DIR.parent / "subtitle-viewer" / "config.json").read_text(encoding="utf-8"))
        src = Path(cfg["src_root"])
    if not args.ecdict.is_file():
        raise SystemExit(f"找不到 ECDICT csv:{args.ecdict}\n下载见 "
                         "https://github.com/skywind3000/ecdict releases,解压后传 --ecdict")
    result = build(src, args.ecdict, args.level)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    s = result["stats"]
    print(f"词池 {s['total']}(已会 {s['known']} · 生词候选 {s['candidate']} · 丢弃 {s['dropped']})"
          f" → {args.out}({args.out.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 跑测试确认通过**(`python -m pytest tests/test_vocab_review.py -q` 全绿)

- [ ] **Step 5: 真数据构建(集成验证,非测试)**

```bash
cd tools/vocab-review && python build.py
```

预期:总词 ~6000±2000、候选生词 1500-3500、vocab.json <1.5MB;异常时看统计调过滤。

- [ ] **Step 6: Commit** `git add tools/vocab-review/build.py tests/test_vocab_review.py && git commit -m "feat(vocab-review): 构建主管线——真数据产出 vocab.json"`

---

### Task 5: SM-2 与队列 `web/core.js`

**Files:**
- Create: `tools/vocab-review/web/core.js`、`tools/vocab-review/web/core.test.js`、空 `tools/vocab-review/web/package.json`(`{"type":"module"}`)

**Interfaces:**
- Produces(ESM export):
  - `newState() -> {e:2.5, i:0, r:0, due:0, g:false}`
  - `answerYes(state, now) -> state'`(r+1;i=r==1?1:r==2?3:round(i×e);due=now+i·86400000;g=r≥4||i≥21)
  - `answerNo(state, now) -> state'`(e=max(1.3,e−0.2);i=0;r=0;due=now+600000;g=false)
  - `buildQueue(words: string[], states: object, now: number, dailyLimit: number, meta) -> {queue: string[], newToday: number}`
    (复习=有状态&&!g&&due≤当日末,按 due 升序;新词=无状态,受 dailyLimit−meta 当日已发 限制)
  - `endOfToday(now) -> number`

- [ ] **Step 1: 写失败测试 core.test.js**

```js
import { test } from "node:test";
import assert from "node:assert/strict";
import { newState, answerYes, answerNo, buildQueue, endOfToday } from "./core.js";

const DAY = 86400000;
test("认识:间隔 1→3→×ease,连认4次毕业", () => {
  let s = newState();
  s = answerYes(s, 0);       assert.equal(s.i, 1);  assert.equal(s.g, false);
  s = answerYes(s, s.due);   assert.equal(s.i, 3);  assert.equal(s.g, false);
  s = answerYes(s, s.due);   assert.equal(s.i, Math.round(3 * 2.5));
  s = answerYes(s, s.due);   assert.equal(s.g, true);
});

test("不认识:重置间隔、降 ease、10分钟后重现", () => {
  let s = answerYes(answerYes(newState(), 0), DAY);
  s = answerNo(s, 2 * DAY);
  assert.equal(s.i, 0); assert.equal(s.r, 0);
  assert.equal(s.e, 2.3); assert.equal(s.due - 2 * DAY, 600000);
});

test("队列:到期复习在前,新词受每日上限", () => {
  const now = Date.now();  // 测试内可用固定数:用 endOfToday 语义断言
  const t = 1700000000000;
  const states = {
    due: { ...newState(), r: 1, i: 1, due: t - DAY },        // 到期
    future: { ...newState(), due: t + 10 * DAY },             // 未到期
    grad: { ...newState(), g: true },                          // 已毕业
  };
  const { queue, newToday } = buildQueue(["due", "future", "grad", "n1", "n2", "n3"],
    states, t, 2, { lastNewDate: "", lastNewCount: 0 });
  assert.deepEqual(queue, ["due", "n1", "n2"]);
  assert.equal(newToday, 2);
  const next = buildQueue(["due", "n3"], states, t, 2,
    { lastNewDate: new Date(t).toDateString(), lastNewCount: 2 });
  assert.deepEqual(next.queue, ["due"]);   // 当日上限已用完
});

test("endOfToday 返回当天 24:00", () => {
  const t = new Date("2026-09-28T09:00:00").getTime();
  assert.equal(endOfToday(t), new Date("2026-09-28T23:59:59.999").getTime());
});
```

- [ ] **Step 2: `node --test web/` 确认失败**(core.js 不存在)

- [ ] **Step 3: 实现 core.js**

```js
/** vocab-review 纯逻辑:SM-2 简化版 + 每日队列。状态:{e,i,r,due,g},词键=词形原形。 */
const DAY = 86400000;

export function newState() { return { e: 2.5, i: 0, r: 0, due: 0, g: false }; }

export function answerYes(state, now) {
  const r = state.r + 1;
  const i = r === 1 ? 1 : r === 2 ? 3 : Math.round(state.i * state.e);
  return { e: state.e, i, r, due: now + i * DAY, g: r >= 4 || i >= 21 };
}

export function answerNo(state, now) {
  return { e: Math.max(1.3, state.e - 0.2), i: 0, r: 0, due: now + 600000, g: false };
}

export function endOfToday(now) {
  const d = new Date(now);
  d.setHours(23, 59, 59, 999);
  return d.getTime();
}

export function buildQueue(words, states, now, dailyLimit, meta) {
  const today = new Date(now).toDateString();
  const used = meta.lastNewDate === today ? meta.lastNewCount : 0;
  const review = [], fresh = [];
  for (const w of words) {
    const s = states[w];
    if (s && !s.g) { if (s.due <= endOfToday(now)) review.push([s.due, w]); }
    else if (!s) fresh.push(w);
  }
  review.sort((a, b) => a[0] - b[0]);
  const newWords = fresh.slice(0, Math.max(0, dailyLimit - used));
  return { queue: [...review.map((x) => x[1]), ...newWords], newToday: used + newWords.length };
}
```

- [ ] **Step 4: `node --test` 确认通过**
- [ ] **Step 5: Commit** `git commit -m "feat(vocab-review): SM-2 与每日队列纯逻辑"`

---

### Task 6: 状态存取与导入导出(core.js 续)

**Files:**
- Modify: `tools/vocab-review/web/core.js`、`core.test.js`(追加)

**Interfaces:**
- Produces:
  - `STORAGE_KEY = "vocab-review-state-v1"`
  - `loadState() -> {states, meta}`(localStorage 不可用/损坏 → `{states:{}, meta:{lastNewDate:"",lastNewCount:0}}`,附 `storageOk:false` 于返回对象)
  - `saveState(box)`;`exportPayload(box, vocabMeta) -> string`(JSON);`mergeImport(current, imported) -> box`(导入为准,结构校验失败抛 `Error("导入文件格式不对")`)

- [ ] **Step 1: 追加失败测试**(用注入的假 storage 对象测纯函数:`serialize`/`mergeImport`;storage 包装只做 try/catch,逻辑全部进纯函数 `mergeImport`)

```js
test("mergeImport 以导入为准且校验结构", () => {
  const cur = { states: { a: newState() }, meta: { lastNewDate: "", lastNewCount: 0 } };
  const imp = { states: { b: { ...newState(), r: 2 } }, meta: { lastNewDate: "x", lastNewCount: 5 } };
  const merged = mergeImport(cur, imp);
  assert.deepEqual(Object.keys(merged.states), ["b"]);
  assert.equal(merged.meta.lastNewCount, 5);
  assert.throws(() => mergeImport(cur, { states: null }), /格式不对/);
});
```

- [ ] **Step 2: 失败 → 实现 → 通过**

```js
export const STORAGE_KEY = "vocab-review-state-v1";

export function emptyBox() {
  return { states: {}, meta: { lastNewDate: "", lastNewCount: 0 } };
}

export function mergeImport(current, imported) {
  if (!imported || typeof imported !== "object"
    || typeof imported.states !== "object" || imported.states === null
    || typeof imported.meta !== "object") {
    throw new Error("导入文件格式不对");
  }
  return { states: { ...imported.states }, meta: { ...imported.meta } };
}

export function loadState() {
  const box = emptyBox();
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) Object.assign(box, JSON.parse(raw));
    box.storageOk = true;
  } catch { box.storageOk = false; }
  return box;
}

export function saveState(box) {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(box)); } catch { /* 隐私模式 */ }
}

export function exportPayload(box, vocabMeta) {
  return JSON.stringify({ exportedAt: new Date().toISOString(), vocab: vocabMeta, ...box }, null, 1);
}
```

- [ ] **Step 3: Commit** `git commit -m "feat(vocab-review): 状态存取/导出导入"`

---

### Task 7: 前端页面(index/app/style,按已确认设计稿)

**Files:**
- Create: `tools/vocab-review/web/index.html`、`app.js`、`style.css`

**Interfaces:**
- Consumes: core.js 全部导出;`vocab.json`(同目录,`{version, words:[{w,phon,def,tags,sents}]}`)
- 页面结构 = 设计稿:统计条(总池/待复习/今日/已毕业)→ 进度条 → 卡片(正面 w+phon+🔊+「显示释义」/背面 def+sents)→ 判定双按钮 → ⚙设置(每日新词、导出/导入)

- [ ] **Step 1: 写 index.html**(按 tmp/vocab_mockup.html 的结构落地:top/stats/progress/flash/judge/hint;卡片与按钮 id:`word/phon/speak/reveal/def/exs/btnNo/btnYes`;设置抽屉 id:`panel`,含 `dailyLimit` 数字输入、`exportBtn`、`importFile`)
- [ ] **Step 2: 写 style.css**(直接采用 mockup 的 :root 变量与全部样式,追加 `#panel` 抽屉与 `.warn` 横幅样式;`@media (min-width:700px)` 卡片区 `max-width:520px` 居中)
- [ ] **Step 3: 写 app.js**(ESM import core;启动流程:fetch vocab.json → loadState → buildQueue → 渲染;翻面/判定/隔10张重现/毕业提示/🔊 speechSynthesis(en-US rate .9)/空格与←→键盘;设置持久化 `vocab-review-settings-v1`;导出用 Blob 下载 `vocab-backup-日期.json`,导入 FileReader→mergeImport→saveState→重渲染)
- [ ] **Step 4: 语法检查与本地冒烟**

```bash
node --check web/app.js && node --test web/
cd web && python -m http.server 8890   # 浏览器开 http://127.0.0.1:8890 手测:翻面/判定/进度/导出/导入/发音
```

- [ ] **Step 5: Commit** `git commit -m "feat(vocab-review): 复习页 UI——卡片/判定/设置/导出导入"`

---

### Task 8: 部署 upload.py + 字幕站入口 + README + 手机验收

**Files:**
- Create: `tools/vocab-review/upload.py`、`tools/vocab-review/README.md`
- Modify: `tools/subtitle-viewer/index.html`(顶栏加「🔤 单词复习」链接 → `/script/vocab/`)

**Interfaces:**
- upload.py:`scp web/index.html app.js core.js style.css vocab.json` → `root@47.108.230.162:/www/.../script/vocab/` + `chown www:www`(路径常量与 sync_subtitles.py 一致:`/www/wwwroot/47.108.230.162/script`)

- [ ] **Step 1: 写 upload.py**(subprocess scp/ssh,逐文件上传,结尾 chown;`--build` 开关先跑 build.py)
- [ ] **Step 2: 写 README.md**(构建/上传/新增文章流程、ECDICT 首次下载、localStorage 与导出导入说明)
- [ ] **Step 3: 字幕站 index.html 顶栏加链接**(不动其他逻辑)
- [ ] **Step 4: 部署并验收**

```bash
cd tools/vocab-review && python upload.py
```

手机打开 http://47.108.230.162/script/vocab/ :复习 5 张卡(认识/不认识各点几个)→ 刷新页面进度保留 → 导出/导入各一次 → 完成后报告用户验收。

- [ ] **Step 5: 全量回归 + Commit**

```bash
python -m pytest tests/ -q && cd tools/vocab-review/web && node --test
git add -A tools/vocab-review tools/subtitle-viewer/index.html
git commit -m "feat(vocab-review): 部署与入口——/script/vocab/ 上线"
```

---

## Self-Review 结论

- 覆盖:spec §3.1→Task 1-4,§3.2/3.3→Task 5-7,§3.4→Task 8,§4 错误处理(loadState 容错/导入校验/构建缺 csv 提示),§5 测试齐 — ✓
- 类型一致:entry `{word,phon,translation,tag,frq,exchange}`、words `{w,phon,def,tags,sents}`、state `{e,i,r,due,g}` 全计划统一 — ✓
- 无占位符 — ✓
