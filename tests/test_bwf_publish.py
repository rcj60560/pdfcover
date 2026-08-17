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
