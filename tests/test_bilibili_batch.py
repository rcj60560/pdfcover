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


def test_run_batch_rescans_requeued_item():
    batch = _mk_batch([1])
    batch.items.append(batch_core.BatchItem(p=2, title="p02", duration=100,
                                            status="failed", attempts=3))
    seen = []

    def on_persist(b):
        # 模拟批量页在 p1 处理期间对失败集 p2 点了「重试」(外部重新入队)
        if b.items[0].status == "running" and b.items[1].status == "failed":
            b.items[1].status = "queued"

    batch_core.run_batch(batch, pipeline=lambda url: seen.append(url) or "r",
                         job_factory=lambda i, r: f"job-{i.p}",
                         sleep=lambda s: None, on_persist=on_persist)
    assert [i.status for i in batch.items] == ["done", "done"]
    assert [i.p for i in batch.items] == [1, 2]
    assert len(seen) == 2 and seen[0].endswith("?p=1") and seen[1].endswith("?p=2")


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
    with pytest.raises(LookupError):
        app_module._job_or_error("nope")


def test_start_batch_thread_guard_against_double_start(monkeypatch, tmp_path):
    import threading as _th
    started = []
    class FakeThread:
        def __init__(self, target, args=(), kwargs=None, daemon=False):
            self.target, self.args, self.kwargs = target, args, kwargs or {}
            self._alive = False
        def start(self):
            started.append(1)
            self._alive = True
        def is_alive(self):
            return self._alive
    monkeypatch.setattr(app_module, "Thread", FakeThread)
    monkeypatch.setattr(app_module, "BATCH_DIR", tmp_path)
    app_module.BATCHES.clear(); app_module.BATCH_THREADS.clear(); app_module.BATCH_JOBS.clear()
    b = batch_core.Batch(batch_id="g1", source_url="u", title="t", created_at="c")
    b.items = [batch_core.BatchItem(p=1, title="p1", duration=60)]
    app_module.BATCHES["g1"] = b
    assert app_module._start_batch_thread(b) is True
    assert app_module._start_batch_thread(b) is False   # 已活线程→拒绝双起
    assert len(started) == 1
