"""ielts-topics 骨架：dev_server 纯逻辑 + 面板清单发现。"""
import importlib.util
import sys
from pathlib import Path

BASE = Path(__file__).parents[1] / "tools" / "ielts-topics"


def _load_dev_server():
    """按路径加载，避免与 speaking-player 的 dev_server 模块名冲突。"""
    spec = importlib.util.spec_from_file_location("ielts_dev_server", BASE / "dev_server.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ds = _load_dev_server()
to_disk = ds.to_disk


def test_to_disk_maps_static_and_index():
    assert to_disk("/").name == "index.html"
    assert to_disk("/data/topics.json") == BASE / "data" / "topics.json"


def test_to_disk_rejects_traversal():
    assert to_disk("/../secret.txt") is None
    assert to_disk("/data/../../secret.txt") is None


def test_manifest_discovers_ielts_topics():
    sys.path.insert(0, str(Path(__file__).parents[1]))
    from launcher.manifest import load_tools

    tools = {t.slug: t for t in load_tools(Path(__file__).parents[1] / "tools")}
    assert tools["ielts-topics"].port == 8500
