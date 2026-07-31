import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dev_server import build_autoindex


def test_build_autoindex_format(tmp_path):
    (tmp_path / "001.mp3").write_bytes(b"")
    (tmp_path / "sub").mkdir()

    result = build_autoindex(str(tmp_path))

    assert isinstance(result, list)
    by_name = {e["name"]: e for e in result}
    assert set(by_name) == {"001.mp3", "sub"}
    assert by_name["001.mp3"]["type"] == "file"
    assert by_name["sub"]["type"] == "directory"
    for e in result:
        assert set(e.keys()) == {"name", "type", "mtime"}
        assert e["mtime"].endswith("GMT")
