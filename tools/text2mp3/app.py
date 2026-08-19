"""text2mp3 网页工具：粘贴文本 → edge-tts（微软神经语音）→ MP3 存到指定文件夹。

用法：
    python app.py [port]      # 默认 8300，面板自动发现

首次使用：pip install -r requirements.txt
"""
from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file, url_for

import tts_core as core

app = Flask(__name__)


async def _synthesize(text: str, voice: str, rate: str, pitch: str, out_path: Path) -> None:
    """调用 edge-tts 生成单个 MP3（同步代码里用 asyncio.run 包）。"""
    import edge_tts  # 延迟导入：纯逻辑单测无需装它

    await edge_tts.Communicate(text, voice, rate=rate, pitch=pitch).save(str(out_path))


@app.get("/")
def index():
    cfg = core.load_config()
    return render_template("index.html", voices=core.VOICES, cfg=cfg)


@app.post("/api/tts")
def api_tts():
    data = request.get_json(force=True)
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify(ok=False, error="请先粘贴要转换的文本"), 400

    voice = data.get("voice") or core.DEFAULT_VOICE
    if voice not in core.VOICES.values():
        return jsonify(ok=False, error=f"未知语音：{voice}"), 400

    out_dir = (data.get("out_dir") or "").strip()
    if not out_dir:
        return jsonify(ok=False, error="请填写输出文件夹"), 400

    rate = core.format_rate(data.get("rate") or 0)
    pitch = core.format_pitch(data.get("pitch") or 0)
    out_path = core.resolve_output_path(out_dir, data.get("filename") or "")
    try:
        asyncio.run(_synthesize(text, voice, rate, pitch, out_path))
    except Exception as exc:  # edge-tts 网络/鉴权失败等，原样带回页面
        return jsonify(ok=False, error=f"合成失败：{exc}"), 500

    core.save_config(voice, int(rate.rstrip("%")), int(pitch.rstrip("Hz")), out_dir)  # 记住本次设置
    return jsonify(ok=True, path=str(out_path), play=url_for("play", p=str(out_path)))


@app.get("/api/play")
def play():
    """页面内试听。只允许当前配置输出目录内的 .mp3，防任意文件读取。"""
    p = Path(request.args.get("p", ""))
    out_dir = Path(core.load_config()["out_dir"]).resolve()
    if p.suffix.lower() != ".mp3" or not p.resolve().is_relative_to(out_dir):
        return "forbidden", 403
    if not p.is_file():
        return "not found", 404
    return send_file(p, mimetype="audio/mpeg")


@app.post("/api/reveal")
def reveal():
    """在资源管理器中定位生成的文件（仅 .mp3 且确实存在）。"""
    p = Path(request.get_json(force=True).get("path") or "")
    if p.suffix.lower() != ".mp3" or not p.is_file():
        return jsonify(ok=False), 400
    subprocess.run(["explorer", "/select,", str(p)], check=False)
    return jsonify(ok=True)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8300
    app.run(host="127.0.0.1", port=port, debug=False)
