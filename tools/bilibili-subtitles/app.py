"""B站字幕提取 → 中英时间轴对齐 → Markdown / Excel。"""
from __future__ import annotations

import sys
from collections import OrderedDict
from dataclasses import dataclass
from io import BytesIO
from threading import Lock
from uuid import uuid4

from flask import Flask, jsonify, render_template, request, send_file

import subtitle_core as core
from extractor import ExtractedVideo, ExtractionError, extract_video
from xlsx_export import build_xlsx


@dataclass
class Job:
    video: ExtractedVideo
    rows: list[core.BilingualRow] | None = None
    english_label: str = ""
    chinese_label: str = ""


class JobStore:
    """本地临时内存缓存；不把 Cookie 或字幕落盘。"""

    def __init__(self, capacity: int = 12) -> None:
        self.capacity = capacity
        self._items: OrderedDict[str, Job] = OrderedDict()
        self._lock = Lock()

    def put(self, job: Job) -> str:
        key = uuid4().hex
        with self._lock:
            self._items[key] = job
            while len(self._items) > self.capacity:
                self._items.popitem(last=False)
        return key

    def get(self, key: str) -> Job | None:
        with self._lock:
            job = self._items.get(key)
            if job is not None:
                self._items.move_to_end(key)
            return job


app = Flask(__name__)
jobs = JobStore()


def _video_public(video: ExtractedVideo) -> dict:
    return {
        "title": video.title,
        "source_url": video.source_url,
        "uploader": video.uploader,
        "duration": video.duration,
        "duration_text": core.format_timestamp(video.duration, milliseconds=False),
    }


def _job_or_error(job_id: str) -> Job:
    job = jobs.get(job_id)
    if job is None:
        raise LookupError("任务已过期，请重新读取字幕")
    return job


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/health")
def health():
    return jsonify(ok=True)


@app.post("/api/inspect")
def inspect_video():
    data = request.get_json(silent=True) or {}
    try:
        video = extract_video(str(data.get("url") or ""), str(data.get("browser") or "none"))
    except (ExtractionError, ValueError) as exc:
        return jsonify(ok=False, error=str(exc)), 400
    job_id = jobs.put(Job(video=video))
    return jsonify(
        ok=True,
        job_id=job_id,
        video=_video_public(video),
        tracks=[track.public_dict() for track in video.tracks],
        suggested=core.suggested_track_ids(video.tracks),
        warnings=list(video.warnings),
    )


@app.post("/api/generate")
def generate():
    data = request.get_json(silent=True) or {}
    try:
        job = _job_or_error(str(data.get("job_id") or ""))
    except LookupError as exc:
        return jsonify(ok=False, error=str(exc)), 404
    by_id = {track.id: track for track in job.video.tracks}
    english_id = str(data.get("english_track") or "")
    chinese_id = str(data.get("chinese_track") or "")
    if english_id and english_id not in by_id:
        return jsonify(ok=False, error="英文字幕轨不存在，请重新读取"), 400
    if chinese_id and chinese_id not in by_id:
        return jsonify(ok=False, error="中文字幕轨不存在，请重新读取"), 400
    english = by_id.get(english_id)
    chinese = by_id.get(chinese_id)
    try:
        rows = core.build_bilingual_rows(english, chinese)
    except ValueError as exc:
        return jsonify(ok=False, error=str(exc)), 400
    if not rows:
        return jsonify(ok=False, error="选择的字幕轨没有有效内容"), 400

    job.rows = rows
    job.english_label = english.label if english else ""
    job.chinese_label = chinese.label if chinese else ""
    has_english = any(row.english for row in rows)
    has_chinese = any(row.chinese for row in rows)
    notice = ""
    if not has_english:
        notice = "当前没有英文字幕轨，英文列将留空。"
    elif not has_chinese:
        notice = "当前没有中文字幕轨，中文列将留空。"
    return jsonify(
        ok=True,
        rows=[row.public_dict() for row in rows],
        count=len(rows),
        has_english=has_english,
        has_chinese=has_chinese,
        notice=notice,
    )


@app.get("/api/jobs/<job_id>/download/<kind>")
def download(job_id: str, kind: str):
    try:
        job = _job_or_error(job_id)
    except LookupError as exc:
        return str(exc), 404
    if not job.rows:
        return "请先生成预览", 400

    basename = core.sanitize_filename(job.video.title) + "-双语字幕"
    if kind == "md":
        content = core.render_markdown(
            job.video.title,
            job.video.source_url,
            job.rows,
            job.english_label,
            job.chinese_label,
        ).encode("utf-8")
        return send_file(
            BytesIO(content), mimetype="text/markdown; charset=utf-8",
            as_attachment=True, download_name=basename + ".md",
        )
    if kind == "xlsx":
        content = build_xlsx(job.video.title, job.video.source_url, job.rows)
        return send_file(
            BytesIO(content),
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True, download_name=basename + ".xlsx",
        )
    return "只支持 md / xlsx", 404


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8600
    app.run(host="127.0.0.1", port=port, debug=False)
