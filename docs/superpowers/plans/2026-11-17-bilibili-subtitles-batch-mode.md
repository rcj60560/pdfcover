# B站字幕工具 · 批量模式 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 合集链接 → 枚举分 P 勾选 → 后端顺序批量拉英文(防限流+断点续跑)→ 每集跳现有阅读页走词典精翻排版。

**Architecture:** 纯加法。新模块 `batch_core.py` 承载全部纯逻辑(数据结构/范围解析/枚举解析/落盘/队列状态机,依赖全注入可离线测试);`app.py` 加 6 个路由 + 批量 job 独立存放(绕开 JobStore 的 LRU-12 淘汰);前端首页加批量面板;单集管线(extractor/direct_generate)零改动。顺带修 alignment_agent 超时孤儿进程 bug。

**Tech Stack:** Python 3.12 / Flask(现有应用) / pytest(离线) / 原生 JS(现有 app.js 风格)。

**Spec:** `docs/superpowers/specs/2026-11-17-bilibili-subtitles-batch-mode-design.md`

## Global Constraints

- 工具真身目录:仓库根的 `tools/bilibili-subtitles/`;测试在仓库根 `tests/`,离线不触网(pytest + monkeypatch,同 `tests/test_bilibili_subtitles.py` 风格)
- **暂存区里有用户自己 staged 的 log-decode 文件,所有 commit 必须用显式 pathspec**(`git commit -m ... -- <files>`),绝不裸 `git add .` / 裸 `git commit`
- 批量 job 不进 `JobStore`(LRU 容量 12 会淘汰),放独立 dict,`_job_or_error` 顺序兜底
- 队列层集间节奏:间隔默认 60s;失败退避 60→300→900s,3 次后标 failed 跳过;转写模型固定 `small.en`、browser 固定 `none`、translate 固定 False(中文待词典)
- 批次落盘目录 `tools/bilibili-subtitles/outputs/batch/`(与现有 outputs/.cache 同级,该目录不入 git)
- 前端文案与现有页面同一语言风格(中文,emoji 徽章)

---

### Task 1: batch_core 数据结构 + 范围解析 + 退避计算

**Files:**
- Create: `tools/bilibili-subtitles/batch_core.py`
- Test: `tests/test_bilibili_batch.py`(新建)

**Interfaces:**
- Produces: `BatchItem`/`Batch` dataclass;`parse_ps(text: str, available: int) -> list[int]`;`backoff_seconds(attempts: int) -> int`;`DEFAULT_INTERVAL_SEC = 60`。后续任务的导入基准:模块名 `batch_core`,通过 `sys.path.insert(0, BASE)` 后 `import batch_core`(与测试文件头部对 subtitle_core 的导入方式一致)。

- [ ] **Step 1: 写失败测试**

新建 `tests/test_bilibili_batch.py`:

```python
"""批量模式纯逻辑测试(离线,不触网)。"""
from __future__ import annotations

import sys
import importlib.util
from pathlib import Path

import pytest

BASE = Path(__file__).parents[1] / "tools" / "bilibili-subtitles"
sys.path.insert(0, str(BASE))

import batch_core  # noqa: E402


def test_parse_ps_ranges_and_singletons():
    assert batch_core.parse_ps("1-3,5", available=10) == [1, 2, 3, 5]
    assert batch_core.parse_ps(" 2 , 4 ", available=10) == [2, 4]
    assert batch_core.parse_ps("3-1", available=10) == [1, 2, 3]  # 反向范围容错为升序


def test_parse_ps_dedup_sort_and_out_of_range_ignore():
    assert batch_core.parse_ps("5,1-3,3", available=5) == [1, 2, 3, 5]
    assert batch_core.parse_ps("1-99", available=6) == [1, 2, 3, 4, 5, 6]  # 越界截断
    assert batch_core.parse_ps("9", available=6) == []  # 全部越界→空


def test_parse_ps_invalid_raises():
    with pytest.raises(ValueError):
        batch_core.parse_ps("abc", available=10)
    with pytest.raises(ValueError):
        batch_core.parse_ps("1--3", available=10)


def test_backoff_seconds_ladder():
    assert batch_core.backoff_seconds(1) == 60
    assert batch_core.backoff_seconds(2) == 300
    assert batch_core.backoff_seconds(3) == 900
    assert batch_core.backoff_seconds(9) == 900  # 上限15分钟


def test_batch_item_defaults():
    item = batch_core.BatchItem(p=6, title="p06", duration=1703)
    assert item.status == "queued" and item.job_id is None
    assert item.error == "" and item.attempts == 0
    b = batch_core.Batch(batch_id="x", source_url="https://www.bilibili.com/video/BV1gK4y1o7Ni", title="系列")
    assert b.interval_sec == batch_core.DEFAULT_INTERVAL_SEC and b.state == "running"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_bilibili_batch.py -v`
Expected: FAIL,`ModuleNotFoundError: No module named 'batch_core'`

- [ ] **Step 3: 最小实现**

新建 `tools/bilibili-subtitles/batch_core.py`:

```python
"""批量模式纯逻辑:数据结构、范围解析、退避、枚举解析、落盘、队列状态机。

无 Flask / 无网络 / 无线程:可注入依赖,离线可测。
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

DEFAULT_INTERVAL_SEC = 60
_BACKOFF_LADDER = (60, 300, 900)  # 1→5→15 分钟,封顶 900


@dataclass
class BatchItem:
    p: int
    title: str
    duration: int
    status: str = "queued"  # queued | running | done | failed
    job_id: str | None = None
    error: str = ""
    attempts: int = 0


@dataclass
class Batch:
    batch_id: str
    source_url: str
    title: str
    items: list[BatchItem] = field(default_factory=list)
    interval_sec: int = DEFAULT_INTERVAL_SEC
    state: str = "running"  # running | finished
    created_at: str = ""


def parse_ps(text: str, available: int) -> list[int]:
    """'1-10,15' → 升序去重的 p 号列表(1 起,越界截断);非法片段抛 ValueError。"""
    result: set[int] = set()
    for raw in (text or "").split(","):
        token = raw.strip()
        if not token:
            continue
        m = re.fullmatch(r"(\d+)\s*-\s*(\d+)|(\d+)", token)
        if not m:
            raise ValueError(f"无法理解的集数范围片段:{token!r}(示例:1-10,15)")
        if m.group(3):
            result.add(int(m.group(3)))
        else:
            lo, hi = sorted((int(m.group(1)), int(m.group(2))))
            result.update(range(lo, hi + 1))
    return sorted(p for p in result if 1 <= p <= available)


def backoff_seconds(attempts: int) -> int:
    """第 attempts 次(1 起)失败后的退避秒数:60→300→900,封顶 900。"""
    if attempts <= 0:
        return 0
    return _BACKOFF_LADDER[min(attempts, len(_BACKOFF_LADDER)) - 1]
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_bilibili_batch.py -v`
Expected: PASS(5 个测试)

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(bilibili-subtitles): 批量模式①——数据结构/范围解析/退避阶梯" -- tools/bilibili-subtitles/batch_core.py tests/test_bilibili_batch.py
```

---

### Task 2: 枚举解析(extract_bvid + view API 响应 → items)

**Files:**
- Modify: `tools/bilibili-subtitles/batch_core.py`
- Test: `tests/test_bilibili_batch.py`(追加)

**Interfaces:**
- Consumes: Task 1 的 `BatchItem`。
- Produces: `extract_bvid(value: str) -> str`;`parse_view_api(payload: dict) -> tuple[str, list[BatchItem]]`。Task 5 的 `/api/batch/list` 依赖这两个函数。

- [ ] **Step 1: 追加失败测试**

```python
def test_extract_bvid_from_url_bv_and_invalid():
    assert batch_core.extract_bvid("https://www.bilibili.com/video/BV1gK4y1o7Ni/?p=8&x=1") == "BV1gK4y1o7Ni"
    assert batch_core.extract_bvid("BV1gK4y1o7Ni") == "BV1gK4y1o7Ni"
    assert batch_core.extract_bvid("bv1gk4y1o7ni?p=4") == "bv1gk4y1o7ni"  # 小写原样保留
    with pytest.raises(ValueError):
        batch_core.extract_bvid("https://www.bilibili.com/video/av170001")


def test_parse_view_api_pages_sorted_to_items():
    payload = {
        "code": 0,
        "data": {
            "title": "【216集完整版】Reading Explorer",
            "pages": [
                {"page": 2, "part": "第二集 标题B", "duration": 1601},
                {"page": 1, "part": "第一集 标题A", "duration": 1703},
            ],
        },
    }
    title, items = batch_core.parse_view_api(payload)
    assert title == "【216集完整版】Reading Explorer"
    assert [i.p for i in items] == [1, 2]
    assert items[0].title == "第一集 标题A" and items[0].duration == 1703


def test_parse_view_api_error_code_raises():
    with pytest.raises(ValueError, match="链接无效或权限不足"):
        batch_core.parse_view_api({"code": -400, "message": "请求错误"})
    with pytest.raises(ValueError, match="B站返回异常数据"):
        batch_core.parse_view_api({"code": 0, "data": {}})
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_bilibili_batch.py -v`
Expected: 新 3 个 FAIL(`AttributeError: ... has no attribute 'extract_bvid'`)

- [ ] **Step 3: 实现(追加到 batch_core.py)**

```python
def extract_bvid(value: str) -> str:
    """从任意输入(BV号/视频页URL含?p=)提取 BV 号;没有则抛 ValueError。"""
    raw = (value or "").strip()
    m = re.search(r"(?i)(BV[0-9A-Za-z]{8,14})", raw)
    if not m:
        raise ValueError("没找到 BV 号:请贴形如 BV1gK4y1o7Ni 的合集/视频链接")
    return m.group(1)


def parse_view_api(payload: dict) -> tuple[str, list[BatchItem]]:
    """B站 view API JSON → (系列标题, 按 p 升序的 BatchItem 列表)。分P标题字段是 part。"""
    if not isinstance(payload, dict) or payload.get("code") != 0:
        message = (payload or {}).get("message") if isinstance(payload, dict) else None
        raise ValueError(f"链接无效或权限不足:B站返回 {message or payload!r:.80}")
    data = payload.get("data") or {}
    pages = data.get("pages") or []
    if not pages:
        raise ValueError("B站返回异常数据:没有分P列表")
    items = [
        BatchItem(p=int(page.get("page") or 0), title=str(page.get("part") or f"p{page.get('page')}"),
                  duration=int(page.get("duration") or 0))
        for page in pages if page.get("page")
    ]
    items.sort(key=lambda i: i.p)
    return str(data.get("title") or ""), items
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_bilibili_batch.py -v`
Expected: PASS(8 个)

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(bilibili-subtitles): 批量模式②——BV提取与view API枚举解析" -- tools/bilibili-subtitles/batch_core.py tests/test_bilibili_batch.py
```

---

### Task 3: 批次持久化(原子写/加载恢复 running→queued)

**Files:**
- Modify: `tools/bilibili-subtitles/batch_core.py`
- Test: `tests/test_bilibili_batch.py`(追加)

**Interfaces:**
- Consumes: Task 1 的 `Batch`。
- Produces: `batch_to_json(batch) -> dict`;`batch_from_json(d) -> Batch`;`save_batch(batch, directory: Path) -> Path`(原子写,返回落盘路径);`load_batches(directory: Path) -> list[Batch]`(扫描全部 json,加载时 items 的 running→queued;坏文件跳过)。Task 4 的 `on_persist` 钩子与 Task 5 的启动加载依赖。

- [ ] **Step 1: 追加失败测试**

```python
def test_batch_persistence_roundtrip_and_running_reset(tmp_path):
    batch = batch_core.Batch(batch_id="ab12", source_url="https://www.bilibili.com/video/BV1gK4y1o7Ni",
                             title="系列", created_at="2026-11-17 10:00:00")
    batch.items = [
        batch_core.BatchItem(p=6, title="p06", duration=1703, status="done", job_id="j1"),
        batch_core.BatchItem(p=7, title="p07", duration=1601, status="running"),
        batch_core.BatchItem(p=8, title="p08", duration=1500, status="failed", error="x", attempts=3),
    ]
    path = batch_core.save_batch(batch, tmp_path)
    assert path.name == "ab12.json" and path.exists()

    loaded = batch_core.load_batches(tmp_path)
    assert len(loaded) == 1
    b = loaded[0]
    assert b.batch_id == "ab12" and b.title == "系列" and b.interval_sec == 60
    assert [i.status for i in b.items] == ["done", "queued", "failed"]  # running→queued
    assert b.items[0].job_id == "j1" and b.items[2].error == "x"


def test_load_batches_skips_corrupt_files(tmp_path):
    (tmp_path / "bad.json").write_text("{not json", encoding="utf-8")
    good = batch_core.Batch(batch_id="cd34", source_url="u", title="t", created_at="c")
    good.items = [batch_core.BatchItem(p=1, title="p1", duration=60)]
    batch_core.save_batch(good, tmp_path)
    loaded = batch_core.load_batches(tmp_path)
    assert [b.batch_id for b in loaded] == ["cd34"]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_bilibili_batch.py -v`
Expected: 新 2 个 FAIL(`AttributeError: ... save_batch`)

- [ ] **Step 3: 实现(追加到 batch_core.py)**

```python
def batch_to_json(batch: Batch) -> dict:
    d = asdict(batch)
    return d


def batch_from_json(d: dict) -> Batch:
    items = [BatchItem(**item) for item in d.get("items", [])]
    # 恢复语义:上次中断时 running 的集子回到排队;done/failed 原样保留
    for item in items:
        if item.status == "running":
            item.status = "queued"
    return Batch(
        batch_id=str(d.get("batch_id") or ""), source_url=str(d.get("source_url") or ""),
        title=str(d.get("title") or ""), items=items,
        interval_sec=int(d.get("interval_sec") or DEFAULT_INTERVAL_SEC),
        state=str(d.get("state") or "finished"), created_at=str(d.get("created_at") or ""),
    )


def save_batch(batch: Batch, directory: Path) -> Path:
    """原子写:先 tmp 后 os.replace,断电不留半个文件。"""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{batch.batch_id}.json"
    tmp = directory / f"{batch.batch_id}.json.tmp"
    tmp.write_text(json.dumps(batch_to_json(batch), ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, target)
    return target


def load_batches(directory: Path) -> list[Batch]:
    out: list[Batch] = []
    for path in sorted(Path(directory).glob("*.json")):
        try:
            out.append(batch_from_json(json.loads(path.read_text(encoding="utf-8"))))
        except (OSError, ValueError, TypeError, KeyError):
            continue  # 坏文件跳过,不拖垮整个启动加载
    return out
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_bilibili_batch.py -v`
Expected: PASS(10 个)

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(bilibili-subtitles): 批量模式③——批次落盘原子写与恢复加载" -- tools/bilibili-subtitles/batch_core.py tests/test_bilibili_batch.py
```

---

### Task 4: 队列状态机 run_batch(全依赖注入)

**Files:**
- Modify: `tools/bilibili-subtitles/batch_core.py`
- Test: `tests/test_bilibili_batch.py`(追加)

**Interfaces:**
- Consumes: Task 1-3 的 `Batch`/`BatchItem`/`save_batch`/`backoff_seconds`。
- Produces: `run_batch(batch: Batch, *, pipeline, job_factory, sleep, on_persist) -> None`。
  - `pipeline(url: str)` → 任意结果对象(成功即 truthy 的完成),抛异常=本集失败
  - `job_factory(item: BatchItem, result) -> str` → 返回 job_id(runner 写进 item.job_id)
  - `sleep(seconds: float)` → 测试注入假实现断言节奏
  - `on_persist(batch: Batch)` → 每次条目状态变更后调用(Task 5 里接 save_batch)
  语义:顺序处理 queued;单集失败 attempts<3 → 退避 sleep 后重试当前集;3 次 → failed 跳过;每成功/跳过处理完一集后(非最后一集)sleep(interval);全部处理完 batch.state='finished'。Task 5 的线程直接调它。

- [ ] **Step 1: 追加失败测试**

```python
class FakeClock:
    def __init__(self):
        self.slept: list[float] = []

    def sleep(self, seconds):
        self.slept.append(seconds)


def _mk_batch(ps, interval=60):
    b = batch_core.Batch(batch_id="t1", source_url="https://www.bilibili.com/video/BV1gK4y1o7Ni",
                         title="T", interval_sec=interval, created_at="c")
    b.items = [batch_core.BatchItem(p=p, title=f"p{p:02d}", duration=100) for p in ps]
    return b


def test_run_batch_happy_path_interval_between_items():
    batch = _mk_batch([1, 2])
    clock = FakeClock()
    made = []

    def job_factory(item, result):
        made.append(item.p)
        return f"job-{item.p}"

    batch_core.run_batch(batch, pipeline=lambda url: f"rows@{url}",
                         job_factory=job_factory, sleep=clock.sleep, on_persist=lambda b: None)
    assert [i.status for i in batch.items] == ["done", "done"]
    assert [i.job_id for i in batch.items] == ["job-1", "job-2"]
    assert made == [1, 2]
    assert clock.slept == [60]  # 只有集间间隔,最后一集后不睡
    assert batch.state == "finished"


def test_run_batch_url_carries_p():
    seen = []

    def pipeline(url):
        seen.append(url)
        return "r"

    batch = _mk_batch([6])
    batch_core.run_batch(batch, pipeline=pipeline, job_factory=lambda i, r: "j",
                         sleep=lambda s: None, on_persist=lambda b: None)
    assert seen == ["https://www.bilibili.com/video/BV1gK4y1o7Ni?p=6"]


def test_run_batch_retry_backoff_then_fail_then_continue():
    batch = _mk_batch([1, 2])
    clock = FakeClock()
    calls = {"1": 0, "2": 0}

    def pipeline(url):
        p = url.split("p=")[1]
        calls[p] += 1
        if p == "1":
            raise RuntimeError("网络被掐")
        return "ok"

    def job_factory(item, result):
        return f"job-{item.p}"

    batch_core.run_batch(batch, pipeline=pipeline, job_factory=job_factory,
                         sleep=clock.sleep, on_persist=lambda b: None)
    assert calls == {"1": 3, "2": 1}                      # 失败集试满3次,下一集1次
    assert batch.items[0].status == "failed" and "网络被掐" in batch.items[0].error
    assert batch.items[1].status == "done"
    assert clock.slept == [60, 300, 60]                   # 第1集退避两轮(60,300),集间60
    assert batch.state == "finished"


def test_run_batch_resume_skips_done_items():
    batch = _mk_batch([1, 2])
    batch.items[0].status, batch.items[0].job_id = "done", "old-job"
    ran = []
    batch_core.run_batch(batch, pipeline=lambda url: ran.append(url) or "r",
                         job_factory=lambda i, r: f"job-{i.p}",
                         sleep=lambda s: None, on_persist=lambda b: None)
    assert ran == ["https://www.bilibili.com/video/BV1gK4y1o7Ni?p=2"]  # done 集不再跑
    assert batch.state == "finished"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_bilibili_batch.py -v`
Expected: 新 4 个 FAIL(`AttributeError: ... run_batch`)

- [ ] **Step 3: 实现(追加到 batch_core.py)**

```python
MAX_ATTEMPTS = 3


def run_batch(batch: Batch, *, pipeline, job_factory, sleep, on_persist) -> None:
    """顺序队列状态机。pipeline/job_factory/sleep/on_persist 全注入,离线可测。

    单集:running→pipeline 成功→job_factory→done;失败 attempts<3→退避后重试当前集;
    3 次→failed 跳过继续。集间(非最后一集)sleep(interval_sec)。全部结束 state=finished。
    """
    pending = [item for item in batch.items if item.status == "queued"]
    for index, item in enumerate(pending):
        is_last = index == len(pending) - 1
        while True:
            item.status, item.error = "running", ""
            on_persist(batch)
            try:
                result = pipeline(f"{batch.source_url}?p={item.p}")
                item.job_id = job_factory(item, result)
                item.status = "done"
                on_persist(batch)
                break
            except Exception as exc:  # noqa: BLE001 - 队列层兜住一切单集失败
                item.attempts += 1
                item.error = str(exc) or exc.__class__.__name__
                if item.attempts >= MAX_ATTEMPTS:
                    item.status = "failed"
                    on_persist(batch)
                    break
                item.status = "queued"
                on_persist(batch)
                sleep(backoff_seconds(item.attempts))
        if not is_last:
            sleep(batch.interval_sec)
    batch.state = "finished"
    on_persist(batch)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_bilibili_batch.py -v`
Expected: PASS(14 个)

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(bilibili-subtitles): 批量模式④——队列状态机(退避/跳过/续跑),全依赖注入" -- tools/bilibili-subtitles/batch_core.py tests/test_bilibili_batch.py
```

---

### Task 5: app.py 接线 —— 6 路由 + 批量 job 独立存放 + 启动加载

**Files:**
- Modify: `tools/bilibili-subtitles/app.py`(顶部 import 区、`_job_or_error`、模块级新增段落、路由区)
- Test: `tests/test_bilibili_batch.py`(追加 Flask test client 用例)

**Interfaces:**
- Consumes: Task 2-4 的 `batch_core` 全部函数;现有 `extractor._download_subtitle(url, headers)`(自带 普通→chrome131→兜底 指纹链);现有 `direct_generate.TRANSCRIBE_PIPELINE` 形态的 `generate_rows_from_audio(url, browser, model_name, log)`;现有 `Job`/`ExtractedVideo`。
- Produces(后端契约,Task 6 前端按此调用):
  - `POST /api/batch/list` `{url}` → `{ok, title, total, items:[{p,title,duration}]}`;失败 `{ok:false, error}`
  - `POST /api/batch/start` `{url, ps:[int], interval:int}` → `{ok, batch_id, total}`(服务端重新枚举一次拿标题,ps 越界/缺失 → 400 带缺失列表)
  - `GET /api/batch/list` → `{ok, batches:[{batch_id,title,state,total,done,failed,resumable,created_at}]}`(resumable = state=="running" 且无活线程)
  - `GET /api/batch/<id>` → `{ok, batch:{...全量 json, items:[...]}}` 或 404
  - `POST /api/batch/<id>/retry` `{p}` → `{ok}`(该集 status=queued/error=""/attempts=0,确保线程在跑)
  - `POST /api/batch/<id>/resume` → `{ok}`(有 queued 且线程没活 → 重起)
  - 批量 job 挂 `BATCH_JOBS: dict[str, Job]`,`_job_or_error` 先查 `jobs` 再查 `BATCH_JOBS` —— 现有 `/api/jobs/<id>/plain-text|auto-align|import-chinese|download/md|transcribe/status` 对批量 job 全部直接可用

- [ ] **Step 1: 追加失败测试(追加到 tests/test_bilibili_batch.py)**

```python
import app as app_module  # noqa: E402  (BASE 已在 sys.path)


@pytest.fixture()
def flask_client(monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "BATCH_DIR", tmp_path)
    app_module.BATCHES.clear()
    app_module.BATCH_THREADS.clear()
    app_module.BATCH_JOBS.clear()
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as client:
        yield client, monkeypatch


def _fake_view_api(monkeypatch, pages, title="系列T"):
    payload = {"code": 0, "data": {"title": title,
               "pages": [{"page": p, "part": f"p{p:02d}", "duration": 100} for p in pages]}}
    monkeypatch.setattr(app_module, "_fetch_view_api", lambda bvid: payload)


def test_batch_list_endpoint_parses_and_sorts(flask_client):
    client, monkeypatch = flask_client
    _fake_view_api(monkeypatch, [2, 1])
    resp = client.post("/api/batch/list", json={"url": "https://www.bilibili.com/video/BV1gK4y1o7Ni?p=8"})
    body = resp.get_json()
    assert body["ok"] and body["total"] == 2
    assert [i["p"] for i in body["items"]] == [1, 2]


def test_batch_start_runs_inline_and_creates_jobs(flask_client, monkeypatch):
    client, mp = flask_client
    _fake_view_api(mp, [1, 2])
    ran = []

    def fake_pipeline(url, browser, model_name, log=None):
        ran.append(url)
        class R:  # 最小 AudioPipelineResult 替身
            rows = [type("Row", (), {"english": "Hello", "chinese": ""})()]
            methods = ["语音识别"]
            title = "t"
        return R()

    mp.setattr(app_module, "TRANSCRIBE_PIPELINE", fake_pipeline)
    mp.setattr(app_module.batch_core, "run_batch", lambda b, **kw: ran.append("run:" + b.batch_id))
    resp = client.post("/api/batch/start", json={"url": "BV1gK4y1o7Ni", "ps": [2, 1], "interval": 30})
    body = resp.get_json()
    assert body["ok"] and body["total"] == 2
    batch_id = body["batch_id"]
    detail = client.get(f"/api/batch/{batch_id}").get_json()["batch"]
    assert [i["p"] for i in detail["items"]] == [1, 2]  # 升序
    assert detail["interval_sec"] == 30
    # 批次文件已落盘
    assert (list(app_module.BATCH_DIR.glob("*.json"))[0].stem) == batch_id


def test_batch_start_missing_ps_rejected(flask_client):
    client, mp = flask_client
    _fake_view_api(mp, [1, 2])
    resp = client.post("/api/batch/start", json={"url": "BV1gK4y1o7Ni", "ps": [1, 9]})
    body = resp.get_json()
    assert not body["ok"] and "9" in body["error"]


def test_batch_job_visible_to_job_or_error(flask_client):
    client, mp = flask_client
    _fake_view_api(mp, [1])
    job = app_module.Job(video=app_module.extractor.ExtractedVideo(
        title="t", source_url="u", uploader="", duration=0, tracks=(), warnings=()))
    app_module.BATCH_JOBS["bj1"] = job
    assert app_module._job_or_error("bj1") is job
    assert app_module._job_or_error("nope")  # 不存在的仍抛 LookupError
```

最后一条写法修正(直取语义,不 assert 返回真值):

```python
def test_batch_job_visible_to_job_or_error(flask_client):
    client, mp = flask_client
    _fake_view_api(mp, [1])
    job = app_module.Job(video=app_module.extractor.ExtractedVideo(
        title="t", source_url="u", uploader="", duration=0, tracks=(), warnings=()))
    app_module.BATCH_JOBS["bj1"] = job
    assert app_module._job_or_error("bj1") is job
    with pytest.raises(LookupError):
        app_module._job_or_error("nope")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_bilibili_batch.py -v`
Expected: 新 4 个 FAIL(`AttributeError: module 'app' has no attribute 'BATCH_DIR'`)

- [ ] **Step 3: 实现 app.py 改动**

3a. 顶部 import 区补:

```python
import batch_core
from extractor import ExtractedVideo
```

(`app.py` 现有 import 布局:标准库 → 第三方 → 本地 `import direct_generate` / `import alignment_agent` / `import extractor as ...`,把这两行放到本地 import 组末尾。)

3b. `_job_or_error`(现约 app.py:288)改为:

```python
def _job_or_error(job_id: str) -> Job:
    job = jobs.get(job_id) or BATCH_JOBS.get(job_id)
    if job is None:
        raise LookupError("任务已过期，请重新读取字幕")
    return job
```

3c. 模块级新增(放在 `jobs = JobStore()` 附近):

```python
# ---- 批量模式:批次注册表 / 批量job独立存放(不进 JobStore 的 LRU,防 216 集把自己挤掉) ----
BATCH_DIR = Path(__file__).resolve().parent / "outputs" / "batch"
BATCHES: dict[str, batch_core.Batch] = {}
BATCH_THREADS: dict[str, Thread] = {}
BATCH_JOBS: dict[str, Job] = {}
_batch_lock = Lock()

for _saved in batch_core.load_batches(BATCH_DIR):  # 启动即恢复(不自动跑,等用户点「恢复」)
    BATCHES[_saved.batch_id] = _saved


def _fetch_view_api(bvid: str) -> dict:
    """一次调用拿全部分P标题/时长。复用 _download_subtitle 的 普通→chrome131 指纹兜底链。"""
    url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
               "Referer": "https://www.bilibili.com/"}
    text = extractor._download_subtitle(url, headers)
    return json.loads(text)
```

(`Path`/`json` 若未导入需补;`extractor` 已在 app.py 导入。)

3d. 路由(放在现有 `/api/jobs/...` 路由之后):

```python
def _batch_public(batch: batch_core.Batch) -> dict:
    done = sum(1 for i in batch.items if i.status == "done")
    failed = sum(1 for i in batch.items if i.status == "failed")
    thread = BATCH_THREADS.get(batch.batch_id)
    return {
        "batch_id": batch.batch_id, "title": batch.title, "state": batch.state,
        "total": len(batch.items), "done": done, "failed": failed,
        "resumable": batch.state == "running" and (thread is None or not thread.is_alive()),
        "created_at": batch.created_at,
    }


def _persist(batch: batch_core.Batch) -> None:
    with _batch_lock:
        batch_core.save_batch(batch, BATCH_DIR)


def _start_batch_thread(batch: batch_core.Batch) -> None:
    def _say_dummy(message):  # 批量集内日志走服务控制台;阅读页日志区留空
        print(f"[batch {batch.batch_id}] {message}", flush=True)

    def _pipeline(url: str):
        return TRANSCRIBE_PIPELINE(url, "none", "small.en", translate=False, log=_say_dummy) \
            if "translate" in TRANSCRIBE_PIPELINE.__code__.co_varnames[:5] \
            else TRANSCRIBE_PIPELINE(url, "none", "small.en", log=_say_dummy)

    def _job_factory(item, result):
        job = Job(video=ExtractedVideo(
            title=f"{item.title}", source_url=f"{batch.source_url}?p={item.p}",
            uploader="", duration=float(item.duration), tracks=(), warnings=()))
        job.rows = result.rows
        english_text, _ = direct_generate.split_methods(result.methods)
        job.english_label = english_text or "语音识别"
        job.chinese_label = "待词典对照"
        job.transcribe.phase = "done"
        job.transcribe.total = len(result.rows)
        job.transcribe.done = len(result.rows)
        with _batch_lock:
            key = uuid4().hex
            BATCH_JOBS[key] = job
        return key

    thread = Thread(
        target=batch_core.run_batch,
        args=(batch,),
        kwargs={"pipeline": _pipeline, "job_factory": _job_factory,
                "sleep": time.sleep, "on_persist": _persist},
        daemon=True,
    )
    BATCH_THREADS[batch.batch_id] = thread
    thread.start()


@app.post("/api/batch/list")  # 注意:与 GET /api/batch/list 同路径不同方法,Flask 各自注册
def batch_list_episodes():
    data = request.get_json(silent=True) or {}
    try:
        bvid = batch_core.extract_bvid(str(data.get("url") or ""))
        title, items = batch_core.parse_view_api(_fetch_view_api(bvid))
    except (ValueError, RuntimeError, OSError) as exc:
        return jsonify(ok=False, error=str(exc)), 400
    return jsonify(ok=True, title=title, total=len(items),
                   items=[{"p": i.p, "title": i.title, "duration": i.duration} for i in items])


@app.get("/api/batch/list")
def batch_list_saved():
    return jsonify(ok=True, batches=[_batch_public(b) for b in BATCHES.values()])


@app.post("/api/batch/start")
def batch_start():
    data = request.get_json(silent=True) or {}
    ps = data.get("ps") or []
    if not isinstance(ps, list) or not ps or not all(isinstance(p, int) for p in ps):
        return jsonify(ok=False, error="请先勾选至少一集"), 400
    try:
        bvid = batch_core.extract_bvid(str(data.get("url") or ""))
        title, items = batch_core.parse_view_api(_fetch_view_api(bvid))
    except (ValueError, RuntimeError, OSError) as exc:
        return jsonify(ok=False, error=str(exc)), 400
    by_p = {i.p: i for i in items}
    missing = [p for p in ps if p not in by_p]
    if missing:
        return jsonify(ok=False, error=f"这些集数在合集里不存在:{','.join(map(str, missing))}"), 400
    batch = batch_core.Batch(
        batch_id=uuid4().hex, source_url=f"https://www.bilibili.com/video/{bvid}",
        title=title, interval_sec=max(10, min(600, int(data.get("interval") or 60))),
        created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )
    batch.items = [batch_core.BatchItem(p=p, title=by_p[p].title, duration=by_p[p].duration)
                   for p in sorted(set(ps))]
    BATCHES[batch.batch_id] = batch
    _persist(batch)
    _start_batch_thread(batch)
    return jsonify(ok=True, batch_id=batch.batch_id, total=len(batch.items))


def _batch_or_error(batch_id: str) -> batch_core.Batch:
    batch = BATCHES.get(batch_id)
    if batch is None:
        raise LookupError("批次不存在或已过期")
    return batch


@app.get("/api/batch/<batch_id>")
def batch_detail(batch_id: str):
    try:
        batch = _batch_or_error(batch_id)
    except LookupError as exc:
        return jsonify(ok=False, error=str(exc)), 404
    return jsonify(ok=True, batch=asdict_public(batch))


def asdict_public(batch: batch_core.Batch) -> dict:
    d = batch_core.batch_to_json(batch)
    return d


@app.post("/api/batch/<batch_id>/retry")
def batch_retry(batch_id: str):
    try:
        batch = _batch_or_error(batch_id)
    except LookupError as exc:
        return jsonify(ok=False, error=str(exc)), 404
    data = request.get_json(silent=True) or {}
    try:
        p = int(data.get("p"))
    except (TypeError, ValueError):
        return jsonify(ok=False, error="缺少集数 p"), 400
    item = next((i for i in batch.items if i.p == p), None)
    if item is None:
        return jsonify(ok=False, error=f"批次里没有第 {p} 集"), 400
    if item.status == "running":
        return jsonify(ok=False, error="这一集正在处理中"), 409
    item.status, item.error, item.attempts = "queued", "", 0
    _persist(batch)
    thread = BATCH_THREADS.get(batch_id)
    if batch.state == "finished":
        batch.state = "running"
        _persist(batch)
    if thread is None or not thread.is_alive():
        _start_batch_thread(batch)
    return jsonify(ok=True)


@app.post("/api/batch/<batch_id>/resume")
def batch_resume(batch_id: str):
    try:
        batch = _batch_or_error(batch_id)
    except LookupError as exc:
        return jsonify(ok=False, error=str(exc)), 404
    if not any(i.status == "queued" for i in batch.items):
        return jsonify(ok=False, error="没有待处理的集数"), 400
    thread = BATCH_THREADS.get(batch_id)
    if thread is not None and thread.is_alive():
        return jsonify(ok=True)  # 已在跑,幂等
    _start_batch_thread(batch)
    return jsonify(ok=True)
```

注意:`TRANSCRIBE_PIPELINE` 在 app.py 顶部 = `direct_generate.generate_rows_from_audio`,签名 `(url, browser, model_name, *, initial_prompt=None, log=None)` — **没有 translate 参数**(translate 是 `_run_transcribe` 外层的概念)。所以 `_pipeline` 直接写死:

```python
    def _pipeline(url: str):
        return TRANSCRIBE_PIPELINE(url, "none", "small.en", log=_say_dummy)
```

(上面 `_start_batch_thread` 里的 if-else 探参版本删掉,用这个确定版本。)

3e. `_batch_public` 中 `Thread`/`uuid4`/`time`/`datetime`/`asdict` 的导入沿用 app.py 现有(`from threading import Lock, Thread` / `from uuid import uuid4` 已存在;`time` 若未导入补 `import time`;`json` 已有)。

- [ ] **Step 4: 跑全量测试确认通过**

Run: `python -m pytest tests/test_bilibili_batch.py tests/test_bilibili_subtitles.py -v`
Expected: 批量 18 个 + 原有 82 个全 PASS(原套件回归确认 `_job_or_error` 改动无副作用)

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(bilibili-subtitles): 批量模式⑤——6路由接线/批量job独立存放绕LRU/启动恢复" -- tools/bilibili-subtitles/app.py tests/test_bilibili_batch.py
```

---

### Task 6: 前端批量面板(index.html + app.js)

**Files:**
- Modify: `tools/bilibili-subtitles/templates/index.html`(单集面板之后加 `<details>`)
- Modify: `tools/bilibili-subtitles/static/app.js`(文件末尾追加批量段)
- Modify: `tools/bilibili-subtitles/static/style.css`(追加批量样式)

**Interfaces:**
- Consumes: Task 5 的 6 个 HTTP 契约;现有 `renderRows(data)`、`state.jobId`、阅读页 DOM(`#reader`)。
- Produces: 无对外接口(终态 UI)。`openBatchJob(jobId)` 供批量表格「去处理」复用。

- [ ] **Step 1: index.html —— 单集面板(`class="panel"` 的外层节点)之后插入:**

```html
<details id="batch-panel" class="panel batch-panel">
  <summary>📦 批量模式 —— 合集勾选,批量拉英文(挂着慢慢跑)</summary>
  <div class="batch-idle">
    <div class="url-row">
      <input id="batch-url" placeholder="贴合集链接或 BV 号,如 BV1gK4y1o7Ni">
      <button id="batch-list-btn" class="primary" type="button">列出集数</button>
    </div>
  </div>
  <div id="batch-episodes" hidden>
    <div class="batch-tools">
      <button id="batch-select-all" type="button">全选</button>
      <button id="batch-clear" type="button">清空</button>
      <input id="batch-range" placeholder="范围,如 1-10,15">
      <button id="batch-range-btn" type="button">按范围勾选</button>
      <label class="batch-interval">集间隔
        <input id="batch-interval" type="number" value="60" min="10" max="600"> 秒
      </label>
      <button id="batch-start" class="primary" type="button">开始批量</button>
    </div>
    <div id="batch-episode-list" class="batch-episode-list"></div>
  </div>
  <div id="batch-run" hidden>
    <div class="batch-progress">
      <div id="batch-progress-text" class="batch-progress-text"></div>
      <div class="batch-bar"><div id="batch-progress-fill" class="batch-bar-fill"></div></div>
    </div>
    <table class="batch-table"><tbody id="batch-tbody"></tbody></table>
  </div>
  <div id="batch-saved-wrap" hidden>
    <h3 class="batch-saved-title">已有批次</h3>
    <div id="batch-saved"></div>
  </div>
</details>
```

(插入位置:阅读区 `#reader` 之前的最后一个面板之后;具体锚点 = 单集模式面板的闭合 `</div>` 后。)

- [ ] **Step 2: style.css 追加:**

```css
/* 批量模式面板 */
.batch-panel summary { cursor: pointer; font-weight: 700; }
.batch-tools { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin: 10px 0; }
.batch-tools input { flex: 0 1 150px; }
.batch-interval { display: flex; gap: 6px; align-items: center; font-size: 13px; }
.batch-interval input { width: 64px; }
.batch-episode-list { max-height: 320px; overflow: auto; border: 1px solid var(--line); border-radius: 10px; }
.batch-episode { display: flex; gap: 10px; align-items: center; padding: 8px 12px; border-bottom: 1px solid var(--line); font-size: 14px; }
.batch-episode:last-child { border-bottom: none; }
.batch-episode .p { color: var(--violet); font-weight: 700; min-width: 44px; }
.batch-episode .t { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.batch-episode .d { color: var(--muted); font-size: 12px; }
.batch-progress-text { font-size: 14px; font-weight: 700; margin-bottom: 6px; }
.batch-bar { height: 10px; border-radius: 999px; background: #ece8f3; overflow: hidden; }
.batch-bar-fill { height: 100%; background: var(--violet); border-radius: 999px; transition: width .4s; }
.batch-table { width: 100%; border-collapse: collapse; font-size: 13px; margin-top: 10px; }
.batch-table td { padding: 7px 8px; border-bottom: 1px solid var(--line); }
.batch-table .st { white-space: nowrap; font-weight: 700; }
.st-done { color: #2e7d32; } .st-failed { color: #c62828; }
.st-running { color: var(--violet); } .st-queued { color: var(--muted); }
.batch-table .op a, .batch-table .op button { color: var(--violet); background: none; border: none; cursor: pointer; font-size: 13px; font-weight: 600; padding: 0; }
.batch-saved-title { margin: 14px 0 6px; font-size: 14px; }
.batch-saved-item { display: flex; gap: 10px; align-items: center; padding: 6px 0; font-size: 13px; }
```

(`--line`/`--violet`/`--muted` 沿用本页已有变量;若名称对不上以 index.html 实际 :root 为准替换。)

- [ ] **Step 3: app.js 末尾追加批量段:**

```js
// ---- 批量模式 ----
const batchState = { episodes: [], batchId: "", timer: null };

function batchStatusBadge(status) {
  return { queued: "⏳ 排队", running: "🔄 进行中", done: "✅ 完成", failed: "❌ 失败" }[status] || status;
}

async function listBatchEpisodes() {
  const url = $("batch-url").value.trim();
  if (!url) return;
  const btn = $("batch-list-btn");
  setBusy(btn, true, "枚举中…", "列出集数");
  try {
    const data = await api("/api/batch/list", { url });
    batchState.episodes = data.items;
    const list = $("batch-episode-list");
    list.replaceChildren();
    data.items.forEach((ep) => {
      const row = document.createElement("label");
      row.className = "batch-episode";
      row.innerHTML = `<input type="checkbox" data-p="${ep.p}">` +
        `<span class="p">p${ep.p}</span><span class="t" title="${ep.title}">${ep.title}</span>` +
        `<span class="d">${Math.round(ep.duration / 60)} 分钟</span>`;
      list.append(row);
    });
    $("batch-episodes").hidden = false;
  } catch (error) {
    setStatus(error.message, "error");
  } finally { setBusy(btn, false, "", "列出集数"); }
}

function checkedBatchPs() {
  return [...document.querySelectorAll("#batch-episode-list input:checked")]
    .map((el) => Number(el.dataset.p));
}

function setBatchChecked(ps) {
  const want = new Set(ps);
  document.querySelectorAll("#batch-episode-list input").forEach((el) => {
    el.checked = want.has(Number(el.dataset.p));
  });
}

async function startBatch() {
  const ps = checkedBatchPs();
  if (!ps.length) { setStatus("先勾选要拉取的集数", "error"); return; }
  const totalMin = batchState.episodes
    .filter((ep) => ps.includes(ep.p))
    .reduce((sum, ep) => sum + ep.duration / 4 + Number($("batch-interval").value || 60), 0) / 60;
  if (ps.length > 30 &&
      !window.confirm(`选中 ${ps.length} 集,预计约 ${Math.round(totalMin)} 分钟(挂机慢跑,可随时停服务暂停)。继续?`)) return;
  const url = $("batch-url").value.trim();
  try {
    const data = await api("/api/batch/start", {
      url, ps, interval: Number($("batch-interval").value || 60),
    });
    batchState.batchId = data.batch_id;
    $("batch-episodes").hidden = true;
    $("batch-run").hidden = false;
    pollBatch();
  } catch (error) { setStatus(error.message, "error"); }
}

function pollBatch() {
  if (batchState.timer) window.clearTimeout(batchState.timer);
  fetch(`/api/batch/${batchState.batchId}`)
    .then((r) => r.json())
    .then((data) => {
      if (!data.ok) return;
      renderBatch(data.batch);
      const unfinished = data.batch.items.filter((i) => i.status === "queued" || i.status === "running").length;
      if (unfinished > 0 || data.batch.state === "running") {
        batchState.timer = window.setTimeout(pollBatch, 3000);
      }
    })
    .catch(() => { batchState.timer = window.setTimeout(pollBatch, 5000); });
}

function renderBatch(batch) {
  const done = batch.items.filter((i) => i.status === "done").length;
  $("batch-progress-text").textContent =
    `${batch.title} —— ${done}/${batch.items.length} 完成` +
    (batch.items.some((i) => i.status === "failed") ? `,${batch.items.filter((i) => i.status === "failed").length} 失败` : "");
  $("batch-progress-fill").style.width = `${(done / batch.items.length) * 100}%`;
  const tbody = $("batch-tbody");
  tbody.replaceChildren();
  batch.items.forEach((item) => {
    const tr = document.createElement("tr");
    const ops = [];
    if (item.status === "done") {
      ops.push(`<a href="javascript:void(0)" onclick="openBatchJob('${item.job_id}')">去处理</a>`);
    } else if (item.status === "failed") {
      ops.push(`<button onclick="retryBatchItem(${item.p})">重试</button>`);
    }
    tr.innerHTML = `<td>p${item.p}</td><td title="${item.title}">${item.title.slice(0, 40)}</td>` +
      `<td class="st st-${item.status}">${batchStatusBadge(item.status)}</td>` +
      `<td class="op">${ops.join(" ")}</td>`;
    tbody.append(tr);
  });
}

async function retryBatchItem(p) {
  try { await api(`/api/batch/${batchState.batchId}/retry`, { p }); pollBatch(); }
  catch (error) { setStatus(error.message, "error"); }
}

async function openBatchJob(jobId) {
  state.jobId = jobId;
  const response = await fetch(`/api/jobs/${jobId}/transcribe/status`);
  const payload = await response.json();
  if (!payload.ok) { setStatus(payload.error || "任务已过期", "error"); return; }
  renderRows({ rows: payload.rows || [], count: (payload.rows || []).length, notice: "" });
}

async function loadSavedBatches() {
  try {
    const response = await fetch("/api/batch/list");
    const data = await response.json();
    const wrap = $("batch-saved");
    wrap.replaceChildren();
    const batches = data.batches || [];
    $("batch-saved-wrap").hidden = !batches.length;
    batches.forEach((b) => {
      const row = document.createElement("div");
      row.className = "batch-saved-item";
      const resume = b.resumable
        ? `<button onclick="resumeBatch('${b.batch_id}')">恢复</button>` : "";
      const view = b.state === "running" || b.done
        ? `<a href="javascript:void(0)" onclick="viewBatch('${b.batch_id}')">查看</a>` : "";
      row.innerHTML = `<b>${b.title.slice(0, 26)}</b><span>${b.done}/${b.total} · ` +
        `${b.state === "finished" ? "已完成" : "未完成"}</span>${view}${resume}`;
      wrap.append(row);
    });
  } catch { /* 静默 */ }
}

async function resumeBatch(batchId) {
  try { await api(`/api/batch/${batchId}/resume`, {}); viewBatch(batchId); }
  catch (error) { setStatus(error.message, "error"); }
}

async function viewBatch(batchId) {
  batchState.batchId = batchId;
  $("batch-episodes").hidden = true;
  $("batch-run").hidden = false;
  pollBatch();
}

$("batch-list-btn").addEventListener("click", listBatchEpisodes);
$("batch-select-all").addEventListener("click", () =>
  setBatchChecked(batchState.episodes.map((ep) => ep.p)));
$("batch-clear").addEventListener("click", () => setBatchChecked([]));
$("batch-range-btn").addEventListener("click", () => {
  // 范围解析在前端复刻 batch_core.parse_ps 语义:1-10,15 → 勾选这些集
  const available = batchState.episodes.length;
  const want = new Set();
  for (const token of $("batch-range").value.split(",")) {
    const m = token.trim().match(/^(\d+)\s*-\s*(\d+)$|^(\d+)$/);
    if (!m) continue;
    if (m[3]) want.add(Number(m[3]));
    else { const [a, b] = [Number(m[1]), Number(m[2])].sort((x, y) => x - y);
      for (let p = a; p <= b; p++) want.add(p); }
  }
  setBatchChecked([...want].filter((p) => p >= 1 && p <= available));
});
$("batch-start").addEventListener("click", startBatch);
loadSavedBatches();
```

(app.js 顶部已有 `$`/`api`/`setBusy`/`setStatus`/`state`/`renderRows` —— 直接复用;若文件末尾已有 DOMContentLoaded 绑定区,把 6 个 addEventListener 与 `loadSavedBatches()` 挪进同一初始化区,保持风格一致。)

- [ ] **Step 4: 启动服务人工冒烟**

Run: `cd tools/bilibili-subtitles && python app.py` → 打开 http://127.0.0.1:8600
Expected:
1. 批量面板默认折叠,展开后贴 `BV1gK4y1o7Ni` → 「列出集数」→ 出现 216 行(p1..p215/216,标题+分钟数)
2. 范围输入 `6-7` → 勾选 p6/p7 → 开始 → 进度表两行,均 ~10 秒内变 ✅(转写缓存秒回)
3. 点 p6「去处理」→ 阅读页打开,分段复制/粘贴区/下载 md 全部可用
4. 重启服务 → 刷新页面 → 「已有批次」出现该批次,「查看」可回看

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(bilibili-subtitles): 批量模式⑥——前端面板(勾选/范围/进度表/去处理/恢复)" -- tools/bilibili-subtitles/templates/index.html tools/bilibili-subtitles/static/app.js tools/bilibili-subtitles/static/style.css
```

---

### Task 7: alignment_agent 修孤儿进程 + 快档可配

**Files:**
- Modify: `tools/bilibili-subtitles/alignment_agent.py`
- Test: `tests/test_bilibili_batch.py`(追加)

**Interfaces:**
- Consumes: 现有 `run_claude_align(prompt, timeout)`。
- Produces: 同名函数(签名不变);新增 `_kill_process_tree(pid: int)`(Windows `taskkill /F /T /PID`,非 Windows `os.kill`);命令构造支持环境变量 `BILISUB_ALIGN_MODEL`(默认 `haiku`;置空字符串则不加 `--model`),claude 调用失败时去掉 `--model` 重试一次(兼容自定义网关没配 haiku 别名的情况)。

- [ ] **Step 1: 追加失败测试**

```python
def test_kill_process_tree_uses_taskkill_on_windows(monkeypatch):
    calls = []
    monkeypatch.setattr(batch_core.os, "name", "nt")
    monkeypatch.setattr(app_module, "subprocess", __import__("types").SimpleNamespace(
        run=lambda cmd, **kw: calls.append(cmd)))
    import alignment_agent
    monkeypatch.setattr(alignment_agent.subprocess, "run",
                        lambda cmd, **kw: calls.append(cmd))
    monkeypatch.setattr(alignment_agent.os, "name", "nt")
    alignment_agent._kill_process_tree(1234)
    assert calls[0][:4] == ["taskkill", "/F", "/T", "/PID"] and calls[0][4] == "1234"


def test_run_claude_align_model_flag_and_fallback(monkeypatch, tmp_path):
    import alignment_agent
    monkeypatch.setattr(alignment_agent.shutil, "which", lambda name: "claude.cmd")
    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        class R: returncode = (1 if len(commands) == 1 else 0); stdout = "OUT"; stderr = ""
        return R()

    monkeypatch.setattr(alignment_agent.subprocess, "run", fake_run)
    monkeypatch.delenv("BILISUB_ALIGN_MODEL", raising=False)
    out = alignment_agent.run_claude_align("PROMPT")
    assert out == "OUT"
    flat = [c for cmd in commands for c in cmd]
    assert "--model" in flat and "haiku" in flat      # 默认快档
    assert any(c == "claude.cmd" for cmd in commands for c in cmd)
    assert "cmd" in commands[0] and "/c" in commands[0]  # .cmd 走 cmd /c 包装
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_bilibili_batch.py -v`
Expected: 新 2 个 FAIL(`AttributeError: _kill_process_tree`)

- [ ] **Step 3: 实现 —— 重写 `run_claude_align`(保留原 docstring 风格)**

```python
def _kill_process_tree(pid: int) -> None:
    """Windows 下 cmd /c 包装的 claude.cmd 超时后,cmd 死了 node 成孤儿——必须杀整棵树。"""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, timeout=10)
        else:
            os.kill(pid, 9)
    except OSError:
        pass


def _build_command(executable: str) -> list[str]:
    command = [executable, "-p", "--output-format", "text"]
    model = os.environ.get("BILISUB_ALIGN_MODEL", "haiku")  # 机械切分任务用快档,不跟全局 max 设置
    if model:
        command += ["--model", model]
    if executable.lower().endswith((".cmd", ".bat")):
        command = ["cmd", "/c", *command]
    return command


def run_claude_align(prompt: str, timeout: int = ALIGN_TIMEOUT_SECONDS) -> str:
    """无头调用本机 claude CLI（stdin 进、stdout 出）；失败给可操作提示。

    超时杀整棵进程树;带 --model 快档失败时去掉该参数裸跑一次(兼容没配该模型别名的网关)。
    """
    executable = shutil.which("claude")
    if not executable:
        raise RuntimeError("未找到 claude 命令——一键排版需要本机已安装 Claude Code 并在 PATH 中")

    def _run(command: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            command, input=prompt, capture_output=True, text=True,
            encoding="utf-8", timeout=timeout,
        )

    try:
        result = _run(_build_command(executable))
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"排版超时（>{timeout} 秒），可重试，或改用「保存，交给 Claude 排版」") from exc
    except OSError as exc:
        raise RuntimeError(f"claude 命令启动失败：{exc}") from exc
    if result.returncode != 0 or not (result.stdout or "").strip():
        if "--model" in _build_command(executable):  # 快档不被网关认识 → 去掉参数裸跑
            try:
                result = _run(_build_command(executable)[:_build_command(executable).index("--model")])
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError(f"排版超时（>{timeout} 秒），可重试，或改用「保存，交给 Claude 排版」") from exc
    output = (result.stdout or "").strip()
    if result.returncode != 0 or not output:
        detail = (result.stderr or "").strip().splitlines()
        hint = detail[-1] if detail else f"退出码 {result.returncode}"
        raise RuntimeError(f"claude 调用失败：{hint}")
    return output
```

顶部 import 补 `import os`(subprocess/shutil 已有)。旧版对 TimeoutExpired 的处理里**没有杀进程**正是孤儿根因,新版由 `_build_command`+`_run` 的结构保证(实现时如需在 TimeoutExpired 里补 `p.kill()` 语义:改用 `subprocess.Popen` + `communicate(timeout)` + except 里 `_kill_process_tree(p.pid)` 再抛,若选此写法则测试断言不变)。

- [ ] **Step 4: 跑全量测试**

Run: `python -m pytest tests/test_bilibili_batch.py tests/test_bilibili_subtitles.py -v`
Expected: 全 PASS

- [ ] **Step 5: Commit**

```bash
git commit -m "fix(bilibili-subtitles): 批量模式⑦——排版无头调用杀进程树修孤儿+快档可配(BILISUB_ALIGN_MODEL)" -- tools/bilibili-subtitles/alignment_agent.py tests/test_bilibili_batch.py
```

---

### Task 8: 真机验收(Reading Explorer)

**Files:** 无新文件(验收任务)

**Interfaces:**
- Consumes: Task 1-7 全部产出。

- [ ] **Step 1: 缓存秒回验收**

服务启动 → 批量面板贴 `BV1gK4y1o7Ni` → 勾 p6、p7(已有转写缓存)→ 间隔 60 → 开始。
Expected: 两集均在 ~15 秒内 ✅(枚举一次 + 缓存命中秒回 + 集间 60s 间隔);批量表格出现两个「去处理」。

- [ ] **Step 2: 新集全链验收**

同批再加勾 p8(无缓存)→ 重试或新开批 → 观察:进行中 🔄 → Whisper 日志在服务控制台滚动 → 数分钟内 ✅;「去处理」→ 阅读页:分段复制(p8 若超 12000 字符应出多个分段按钮)→ 粘贴区 → 一键排版 → 下载 md。

- [ ] **Step 3: 断点续跑验收**

Step 2 进行中停服务(页面右上「停止服务」)→ 重新 `python app.py` → 刷新 → 「已有批次」该批显示「恢复」→ 点恢复 → p8 从 queued 继续跑(已 done 的 p6/p7 不重跑);最终 md 与直跑结果一致。

- [ ] **Step 4: 失败路径验收(可选,拔网线/断热点模拟)**

拉一批 2 集后断网:集 1 失败 → 服务控制台可见退避节奏(60s→300s→900s)→ 3 次后 ❌ 跳过集 2 → 恢复网络 → 批量页点集 1「重试」→ ✅。

- [ ] **Step 5: 收尾**

全部通过后把 `tools/bilibili-subtitles/README.md` 的使用节补一段批量模式说明(约 8 行:入口/勾选/间隔/恢复/批次文件位置),并:

```bash
git commit -m "docs(bilibili-subtitles): 批量模式使用说明" -- tools/bilibili-subtitles/README.md
```

---

## Self-Review 记录

- **Spec 覆盖**:§二架构(Task 5/6)、§三数据结构+落盘恢复(Task 1/3/5)、§四队列三件套(Task 4)、§五 API(Task 5,补了 spec 未列的 `/resume` 作为 §三「用户点恢复才重起线程」的载体)、§六前端(Task 6)、§七小修(Task 7)、§八测试(各任务+Task 8)、§九 YAGNI 未做。无缺口。
- **占位符扫描**:无 TBD/TODO;所有代码块完整可落地。
- **类型一致性**:`run_batch(batch, *, pipeline, job_factory, sleep, on_persist)` 在 Task 4 定义、Task 5 以同参调用;`BatchItem` 字段名 p/title/duration/status/job_id/error/attempts 全文一致;`_fetch_view_api`/`BATCH_DIR`/`BATCHES`/`BATCH_THREADS`/`BATCH_JOBS` 命名在 Task 5 测试与实现一致,Task 6 前端只走 HTTP 不碰这些名。
