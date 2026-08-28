import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "tools" / "bwf-data"))
from publish import validate


def _rankings(n=50):
    return {"disciplines": {k: {"name": k, "entries": [{"rank": i} for i in range(n)]}
                            for k in ("ms", "ws", "md", "wd", "xd")}}


def _schedule(n=25):
    return {"year": 2026, "tournaments": [{"name": f"t{i}"} for i in range(n)]}


def test_validate_ok():
    validate(_rankings(), _schedule())  # 不抛即通过


def test_validate_missing_discipline():
    bad = _rankings(); bad["disciplines"].pop("xd")
    with pytest.raises(AssertionError):
        validate(bad, _schedule())


def test_validate_too_few_rows():
    with pytest.raises(AssertionError):
        validate(_rankings(n=10), _schedule())


def test_validate_too_few_tournaments():
    with pytest.raises(AssertionError):
        validate(_rankings(), _schedule(n=3))


def test_run_all_flags_wired_to_publish():
    """--push 必须经 run_all 的 argparse 接通到 publish.main(push=...)，防再退化成无人能置位的死旗标"""
    import run_all

    parser = run_all.build_parser()
    both = parser.parse_args(["--publish", "--push"])
    assert both.publish is True and both.push is True
    publish_only = parser.parse_args(["--publish"])
    assert publish_only.publish is True and publish_only.push is False
    defaults = parser.parse_args([])
    assert defaults.publish is False and defaults.push is False
