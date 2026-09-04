"""word2md 纯逻辑单测 + pandoc 在机时的集成用例（未装则自动跳过）。"""
import io
import shutil
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "tools" / "word2md"))
import word2md_core as core  # noqa: E402

HAS_PANDOC = shutil.which("pandoc") is not None

# 1x1 PNG
_PNG = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
        b'\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0'
        b'\xf0\x1f\x00\x05\x05\x02\x00_\xc8\xf1\xd2\x00\x00\x00\x00IEND\xaeB`\x82')


def make_docx(path: Path, with_image: bool = True) -> Path:
    """手工构造最小 .docx（一级标题 + 段落 + 可选内嵌图片），不依赖 python-docx。"""
    drawing = ('<w:p><w:r><w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0">'
               '<wp:extent cx="952500" cy="952500"/><wp:docPr id="1" name="图1"/>'
               '<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
               '<pic:pic><pic:nvPicPr><pic:cNvPr id="1" name="图1"/><pic:cNvPicPr/></pic:nvPicPr>'
               '<pic:blipFill><a:blip r:embed="rId4"/></pic:blipFill><pic:spPr/></pic:pic>'
               '</a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>'
               ) if with_image else ""
    doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
           'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
           'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
           'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
           'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
           '<w:body>'
           '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>标题一</w:t></w:r></w:p>'
           '<w:p><w:r><w:t>正文中文字测试。</w:t></w:r></w:p>'
           f'{drawing}'
           '<w:sectPr/></w:body></w:document>')
    ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
          '<Default Extension="xml" ContentType="application/xml"/>'
          '<Default Extension="png" ContentType="image/png"/>'
          '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
          '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
          '</Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            '</Relationships>')
    doc_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
                + ('<Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/image1.png"/>'
                   if with_image else "")
                + '</Relationships>')
    styles = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
              '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/></w:style>'
              '</w:styles>')
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", ct)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/document.xml", doc)
        z.writestr("word/_rels/document.xml.rels", doc_rels)
        z.writestr("word/styles.xml", styles)
        if with_image:
            z.writestr("word/media/image1.png", _PNG)
    return path


# ---------- 纯逻辑 ----------

def test_resolve_paths_defaults(tmp_path):
    docx = make_docx(tmp_path / "说明书.docx", with_image=False)
    p = core.resolve_paths(docx)
    assert p.out == tmp_path / "说明书.md"
    assert p.media == tmp_path / core.DEFAULT_MEDIA_DIR


def test_resolve_paths_docx_inside_media_folder(tmp_path):
    """docx 躺在 图片和附件/ 里：md 放上一级并复用该目录存图（devdocs 归档习惯）。"""
    folder = tmp_path / "需求" / core.DEFAULT_MEDIA_DIR
    folder.mkdir(parents=True)
    docx = make_docx(folder / "说明书.docx", with_image=False)
    p = core.resolve_paths(docx)
    assert p.out == tmp_path / "需求" / "说明书.md"
    assert p.media == folder


def test_resolve_paths_overrides(tmp_path):
    docx = make_docx(tmp_path / "a.docx", with_image=False)
    p = core.resolve_paths(docx, output_md=tmp_path / "out" / "b.txt", media_dir="assets")
    assert p.out == tmp_path / "out" / "b.md"          # 后缀强制 .md
    assert p.media == tmp_path / "out" / "assets"       # 相对 media 目录锚定在输出目录


def test_doc_rejected_with_saveas_hint(tmp_path):
    old = tmp_path / "老文档.doc"
    old.write_bytes(b"\xd0\xcf\x11\xe0")               # OLE2 魔数
    with pytest.raises(core.NotDocxError, match="另存为 .docx"):
        core.resolve_paths(old)
    txt = tmp_path / "笔记.txt"
    txt.write_text("x", encoding="utf-8")
    with pytest.raises(core.NotDocxError, match="只支持 .docx"):
        core.resolve_paths(txt)


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        core.resolve_paths(tmp_path / "不存在.docx")


def test_pandoc_missing_hint(monkeypatch):
    monkeypatch.setattr(core.shutil, "which", lambda _: None)
    with pytest.raises(core.PandocNotFound, match="pandoc"):
        core.find_pandoc()


def test_build_command_shape(tmp_path):
    docx = make_docx(tmp_path / "说明书.docx", with_image=False)
    p = core.resolve_paths(docx)
    cmd = core.build_command("pandoc", p)
    assert cmd[0] == "pandoc" and str(docx.resolve()) in cmd
    assert "-t" in cmd and cmd[cmd.index("-t") + 1] == "gfm"
    assert "--wrap=none" in cmd
    assert cmd[cmd.index("-o") + 1] == "说明书.md"       # 输出/抽图均为相对名（cwd=输出目录）
    assert cmd[cmd.index("--extract-media") + 1] == core.DEFAULT_MEDIA_DIR


def test_rewrite_md_flattens_media_and_img(tmp_path):
    md = tmp_path / "x.md"
    md.write_text(
        '<img src="图片和附件/media/image1.png" style="width:1in" />\n'
        '<img src="图片和附件/media/image2.png" alt="示意图" />',
        encoding="utf-8",
    )
    core.rewrite_md(md, core.DEFAULT_MEDIA_DIR)
    text = md.read_text(encoding="utf-8")
    assert "![](图片和附件/image1.png)" in text            # 无 media/ 子层、md 原生图片
    assert "![示意图](图片和附件/image2.png)" in text       # alt 文本保留
    assert "<img" not in text and "/media/" not in text


# ---------- 集成（需本机 pandoc） ----------

@pytest.mark.skipif(not HAS_PANDOC, reason="本机未安装 pandoc")
def test_convert_end_to_end_with_image(tmp_path):
    docx = make_docx(tmp_path / "说明书.docx", with_image=True)
    r = core.convert(docx)
    assert r.md == tmp_path / "说明书.md" and r.md.is_file()
    assert r.images == 1 and r.media == tmp_path / core.DEFAULT_MEDIA_DIR
    assert (tmp_path / core.DEFAULT_MEDIA_DIR / "image1.png").read_bytes() == _PNG  # 已拍平
    text = r.md.read_text(encoding="utf-8")
    assert text.startswith("# 标题一")                     # 标题样式生效
    assert "正文中文字测试。" in text
    assert "![](图片和附件/image1.png)" in text
    assert "<img" not in text and "/media/" not in text


@pytest.mark.skipif(not HAS_PANDOC, reason="本机未安装 pandoc")
def test_convert_without_image_leaves_no_media_dir(tmp_path):
    docx = make_docx(tmp_path / "纯文字.docx", with_image=False)
    r = core.convert(docx)
    assert r.images == 0 and r.media is None
    assert not (tmp_path / core.DEFAULT_MEDIA_DIR).exists()  # 无图不留空目录


@pytest.mark.skipif(not HAS_PANDOC, reason="本机未安装 pandoc")
def test_convert_reused_media_folder_counts_only_images(tmp_path):
    """复用 图片和附件/：源 docx 不是图片，不计入；目录里有非空内容也不误删。"""
    folder = tmp_path / "需求" / core.DEFAULT_MEDIA_DIR
    folder.mkdir(parents=True)
    docx = make_docx(folder / "说明书.docx", with_image=False)
    r = core.convert(docx)
    assert r.md == tmp_path / "需求" / "说明书.md"
    assert r.images == 0 and r.media is None
    assert docx.is_file() and folder.is_dir()      # 源文件与目录原样保留


@pytest.mark.skipif(not HAS_PANDOC, reason="本机未安装 pandoc")
def test_convert_twice_overwrites(tmp_path):
    docx = make_docx(tmp_path / "说明书.docx", with_image=True)
    core.convert(docx)
    core.convert(docx)                                       # 重转：图片同名覆盖不报错
    assert len(list((tmp_path / core.DEFAULT_MEDIA_DIR).iterdir())) == 1


def test_manifest_discovers_word2md():
    sys.path.insert(0, str(Path(__file__).parents[1]))
    from launcher.manifest import load_tools

    tools = {t.slug: t for t in load_tools(Path(__file__).parents[1] / "tools")}
    tool = tools["word2md"]
    assert tool.status == "ready"
    assert tool.port == 8700
    assert tool.url == "http://127.0.0.1:8700"
    assert tool.name == "Word→Markdown"


# ---------- 网页版（test_client，不起服） ----------

@pytest.mark.skipif(not HAS_PANDOC, reason="本机未安装 pandoc")
def test_web_convert_zip_and_rejects(tmp_path, monkeypatch):
    import app as web
    monkeypatch.setattr(web, "OUT_DIR", tmp_path / "out")    # 产物不落仓库
    client = web.app.test_client()

    assert client.get("/").status_code == 200

    docx = make_docx(tmp_path / "说明书.docx", with_image=True)
    rv = client.post("/api/convert",
                     data={"file": (docx.open("rb"), "说明书.docx")},
                     content_type="multipart/form-data")
    j = rv.get_json()
    assert rv.status_code == 200 and j["ok"]
    assert "# 标题一" in j["md_text"]
    assert j["images"] == ["image1.png"]
    assert (Path(j["out_dir"]) / "说明书.md").is_file()

    z = client.get(j["zip_url"])
    assert z.status_code == 200 and z.data[:2] == b"PK"

    for name, blob, expect in [("老文档.doc", b"\xd0\xcf", "另存为 .docx"),
                               ("笔记.txt", b"x", "只支持 .docx")]:
        rv = client.post("/api/convert", data={"file": (io.BytesIO(blob), name)},
                         content_type="multipart/form-data")
        assert rv.status_code == 400 and expect in rv.get_json()["error"]


def test_web_paths_are_jailed(tmp_path, monkeypatch):
    """zip 只认合法 token；reveal 只允许 out/ 内的绝对路径。"""
    import app as web
    monkeypatch.setattr(web, "OUT_DIR", tmp_path)
    client = web.app.test_client()
    assert client.get("/api/zip/nothex!").status_code == 403
    assert client.get("/api/zip/000000000000").status_code == 404
    rv = client.post("/api/reveal", json={"path": r"C:\Windows"})
    assert rv.status_code == 403
