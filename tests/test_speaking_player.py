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
