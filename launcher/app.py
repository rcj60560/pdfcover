"""Flask 总入口面板：列出工具卡片，启动/打开/停止。"""
from __future__ import annotations

import time
from pathlib import Path

from flask import Flask, jsonify, render_template

from .manifest import load_tools
from .probe import port_open
from .processes import registry

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"


def _find(slug: str):
    return next((t for t in load_tools(TOOLS) if t.slug == slug), None)


def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/")
    def index():
        tools = load_tools(TOOLS)
        statuses = {t.slug: registry.is_running(t.slug, t.port) for t in tools}
        return render_template("index.html", tools=tools, statuses=statuses)

    @app.post("/launch/<slug>")
    def launch(slug):
        t = _find(slug)
        if not t or not t.cmd or t.status != "ready":
            return ("not runnable", 404)
        if not registry.is_running(slug, t.port):
            registry.start(slug, t.cmd, t.dir, t.port)
        if t.port:
            for _ in range(40):  # 最多等 ~10s 起服
                if port_open(t.port):
                    break
                time.sleep(0.25)
        return jsonify({"url": t.url, "running": registry.is_running(slug, t.port)})

    @app.post("/stop/<slug>")
    def stop(slug):
        return jsonify({"stopped": registry.stop(slug)})

    @app.get("/status/<slug>")
    def status(slug):
        t = _find(slug)
        running = registry.is_running(slug, t.port) if t and t.port else False
        return jsonify({"running": running})

    return app
