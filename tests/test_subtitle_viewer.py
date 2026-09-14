"""subtitle-viewer：subtitle_lib 纯逻辑 + dev_server + 面板清单发现。"""
import sys
from pathlib import Path

TOOL = Path(__file__).parents[1] / "tools" / "subtitle-viewer"
sys.path.insert(0, str(TOOL))
# 全量跑测时 speaking-player 等工具的同名 dev_server 已缓存进 sys.modules；清掉，让下面的导入用本工具的
for _stale in ("dev_server", "subtitle_lib", "sync_subtitles"):
    sys.modules.pop(_stale, None)


def test_parse_ts():
    from subtitle_lib import parse_ts
    assert parse_ts("00:00:06") == 6
    assert parse_ts("0:06") == 6
    assert parse_ts("01:02:03") == 3723
    assert parse_ts("62:05") == 3725


def test_has_timestamps():
    from subtitle_lib import has_timestamps
    assert has_timestamps("`00:00:00 → 00:00:06`")
    assert has_timestamps("前言\n\n`3:10 → 3:20`\n\n**a**\n")
    assert not has_timestamps("# 只有标题\n\n普通文本，没有时间戳。")


GOOD_MD = "# 标题\n\n> 来源说明\n\n---\n\n`00:00:00 → 00:00:06`\n\n**Hello.**\n\n你好。\n\n---\n\n`00:00:08 → 00:00:14`\n\n**World.**\n\n世界。\n"


def test_collect_docs(tmp_path):
    from subtitle_lib import collect_docs
    (tmp_path / "in-use" ).mkdir()
    (tmp_path / "in-use" / "Unit 1.md").write_text(GOOD_MD, encoding="utf-8")
    (tmp_path / "plain.md").write_text("# 无时间戳\n", encoding="utf-8")
    (tmp_path / "_private").mkdir()
    (tmp_path / "_private" / "x.md").write_text(GOOD_MD, encoding="utf-8")

    docs = collect_docs(tmp_path)
    assert [d["path"] for d in docs] == ["in-use/Unit 1.md"]
    assert docs[0]["title"] == "Unit 1"
    assert docs[0]["count"] == 2
    assert docs[0]["duration"] == 14


def test_collect_docs_natural_order(tmp_path):
    from subtitle_lib import collect_docs
    for n in [
        "Vocabulary｜Unit 10 全英导学.md",
        "Vocabulary｜Unit 2 全英讲解.md",
        "Vocabulary｜Unit 8 全英导学 Part 2.md",
        "Vocabulary｜Unit 1 全英讲解.md",
        "Vocabulary｜Unit 8 全英导学 Part 1.md",
    ]:
        (tmp_path / n).write_text(GOOD_MD, encoding="utf-8")
    assert [d["title"] for d in collect_docs(tmp_path)] == [
        "Vocabulary｜Unit 1 全英讲解",
        "Vocabulary｜Unit 2 全英讲解",
        "Vocabulary｜Unit 8 全英导学 Part 1",
        "Vocabulary｜Unit 8 全英导学 Part 2",
        "Vocabulary｜Unit 10 全英导学",
    ]


def test_resolve_docs_dir(tmp_path):
    from dev_server import resolve_docs_dir
    cfg = tmp_path / "config.json"
    real = tmp_path / "real"; real.mkdir()
    cfg.write_text('{"src_root": "%s"}' % str(real).replace("\\", "\\\\"), encoding="utf-8")
    assert resolve_docs_dir(cfg, tmp_path / "fallback") == real
    cfg.write_text('{"src_root": "Z:\\\\不存在的目录"}', encoding="utf-8")
    assert resolve_docs_dir(cfg, tmp_path / "fallback") == tmp_path / "fallback"
    assert resolve_docs_dir(tmp_path / "没有.json", tmp_path / "fallback") == tmp_path / "fallback"


def test_to_disk_maps_docs(tmp_path):
    from dev_server import to_disk
    assert to_disk("/docs/", tmp_path) == tmp_path
    assert to_disk("/docs", tmp_path) == tmp_path
    assert to_disk("/docs/a%20b.md", tmp_path) == tmp_path / "a b.md"
    assert to_disk("/").name == "index.html"
    assert to_disk("/manifest.json").name == "manifest.json"


def test_to_disk_rejects_traversal(tmp_path):
    import pytest
    from dev_server import to_disk
    for bad in ("/docs/..%2F..%2Fx.md", "/docs/a/../../../x.md", "/..%5C..%5Cx.md", "/docs/..%5Cx.md",
                "/docs/c:%2Fx.md", "/docs/%5C%5Cserver%5Cshare%5Cx.md", "/%5C%5Cserver%5Cshare%5Cx.md"):
        with pytest.raises(ValueError):
            to_disk(bad, tmp_path)


def test_sync_front_files_and_read_src(tmp_path):
    import sync_subtitles
    files = sync_subtitles.front_files(TOOL)
    assert [f.name for f in files] == ["index.html", "app.js", "core.js", "style.css"]

    cfg = tmp_path / "config.json"
    real = tmp_path / "real"; real.mkdir()
    cfg.write_text('{"src_root": "%s"}' % str(real).replace("\\", "\\\\"), encoding="utf-8")
    assert sync_subtitles.read_src(cfg) == real
    assert sync_subtitles.read_src(tmp_path / "没有.json") == TOOL / "fixtures" / "docs"


def test_manifest_discovers_subtitle_viewer():
    sys.path.insert(0, str(Path(__file__).parents[1]))
    from launcher.manifest import load_tools

    tools = {t.slug: t for t in load_tools(Path(__file__).parents[1] / "tools")}
    assert tools["subtitle-viewer"].port == 8800
    assert tools["subtitle-viewer"].status == "ready"
