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
