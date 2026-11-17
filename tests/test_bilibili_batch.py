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
