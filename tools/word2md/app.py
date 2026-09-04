"""word2md 网页工具：上传 .docx → pandoc → Markdown 预览 / zip 下载。

用法：
    python app.py [port]      # 默认 8700，面板自动发现
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import time
import uuid
import zipfile
from io import BytesIO
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file, url_for

import word2md_core as core

app = Flask(__name__)
OUT_DIR = Path(__file__).resolve().parent / "out"
TOKEN_RE = re.compile(r"^[0-9a-f]{12}$")   # 每次转换的产物目录名（uuid 前 12 位）


def _cleanup_old(hours: float = 24.0) -> None:
    """转换前顺手清掉 24h 前的历史产物，out/ 不无限膨胀。"""
    if not OUT_DIR.is_dir():
        return
    deadline = time.time() - hours * 3600
    for d in OUT_DIR.iterdir():
        if d.is_dir() and d.stat().st_mtime < deadline:
            shutil.rmtree(d, ignore_errors=True)


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/convert")
def api_convert():
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify(ok=False, error="请先选择 .docx 文件"), 400
    suffix = Path(f.filename).suffix.lower()
    if suffix == ".doc":
        return jsonify(ok=False, error="老版 .doc 请先用 Word/WPS 另存为 .docx 再上传"), 400
    if suffix != ".docx":
        return jsonify(ok=False, error="只支持 .docx 文件"), 400

    _cleanup_old()
    token = uuid.uuid4().hex[:12]
    work = OUT_DIR / token
    work.mkdir(parents=True, exist_ok=True)
    src = work / Path(f.filename).name      # .name 防路径穿越
    f.save(src)
    try:
        r = core.convert(src)
    except Exception as exc:                # pandoc 失败等，原样带回页面
        shutil.rmtree(work, ignore_errors=True)
        return jsonify(ok=False, error=str(exc)), 500

    images = sorted(p.name for p in r.media.iterdir()) if r.media else []
    return jsonify(ok=True, token=token, out_dir=str(work),
                   md_text=r.md.read_text(encoding="utf-8"), images=images,
                   zip_url=url_for("api_zip", token=token))


@app.get("/api/zip/<token>")
def api_zip(token: str):
    """打包下载该次转换的全部产物（md + 图片和附件/）。"""
    if not TOKEN_RE.match(token):
        return "forbidden", 403
    work = (OUT_DIR / token).resolve()
    if not work.is_relative_to(OUT_DIR.resolve()) or not work.is_dir():
        return "not found", 404
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(work.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(work))
    buf.seek(0)
    return send_file(buf, mimetype="application/zip", as_attachment=True,
                     download_name=f"{token}.zip")


@app.post("/api/reveal")
def reveal():
    """在资源管理器中定位产物（只允许 out/ 内的路径，防任意目录探测）。"""
    p = Path(request.get_json(force=True).get("path") or "")
    if not p.is_absolute() or not p.resolve().is_relative_to(OUT_DIR.resolve()):
        return jsonify(ok=False), 403
    if not p.exists():
        return jsonify(ok=False), 404
    subprocess.run(["explorer", "/select,", str(p)], check=False)
    return jsonify(ok=True)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8700
    app.run(host="127.0.0.1", port=port, debug=False)
