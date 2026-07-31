import textwrap
from pathlib import Path

from launcher.manifest import load_tools, Tool


def _make(tmp_path: Path, slug: str, body: str) -> None:
    d = tmp_path / slug
    d.mkdir()
    (d / "tool.toml").write_text(textwrap.dedent(body), encoding="utf-8")


def test_load_ready_and_planned(tmp_path):
    _make(tmp_path, "pdf-ocr", """
        name = "PDF OCR"
        desc = "d"
        category = "文档"
        status = "ready"
        [run]
        cmd = ["python", "-m", "pdfcover.web"]
        port = 5000
        url = "http://127.0.0.1:5000"
        [links]
        live = ""
    """)
    _make(tmp_path, "dics", """
        name = "词典"
        desc = "d2"
        category = "英语"
        status = "planned"
    """)
    tools = load_tools(tmp_path)
    assert [t.slug for t in tools] == ["dics", "pdf-ocr"]  # 按 slug 排序
    ready = tools[1]
    assert isinstance(ready, Tool)
    assert ready.status == "ready"
    assert ready.cmd == ["python", "-m", "pdfcover.web"]
    assert ready.port == 5000
    assert ready.url == "http://127.0.0.1:5000"
    assert ready.name == "PDF OCR"
    planned = tools[0]
    assert planned.status == "planned"
    assert planned.cmd == [] and planned.port is None


def test_skip_underscore_and_no_manifest(tmp_path):
    _make(tmp_path, "_template", 'name = "t"\ndesc = ""\ncategory = ""\nstatus = "ready"\n')
    (tmp_path / "nope").mkdir()  # 无 tool.toml
    assert load_tools(tmp_path) == []
