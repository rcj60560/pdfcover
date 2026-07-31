# my-toolkit 工具箱重组 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `pdfcover` 仓库重组为个人工具箱 `my-toolkit`：`tools/<工具>/` 统一布局 + Flask 总入口面板（点工具即启动并跳转）+ `tool.toml` 清单驱动，全程 `git mv` 保留历史。

**Architecture:** 顶层只放 launcher（Flask 面板）+ 总 README；每个工具自包含在 `tools/<slug>/`，带一个 `tool.toml` 清单。launcher 启动时扫描 `tools/*/tool.toml` 渲染卡片，【启动】以 `cwd=工具目录` 拉起该工具命令并跳转到其 url。加新工具零改 launcher。

**Tech Stack:** Python 3.10+、Flask（面板）、tomllib(3.11+)/tomli(3.10)（解析 tool.toml）、现有 pdfcover（Flask+ocrmypdf）、现有 audioplayer（静态站+dev_server.py）。

## Global Constraints

- 保留 git 历史：仓库内搬迁一律 `git mv`；gitignore 的数据（books/、coverdPDF/、egg-info、缓存、日志）用普通 `mv`，无历史问题。
- `pdfcover` 这个 Python 包名不改（`python -m pdfcover.web`、`pip install` 仍依赖它）；只改项目/文件夹名。
- launcher 纯逻辑（manifest 解析、端口探测）走单测；Flask 路由/进程管理走端到端手测。
- 全程在分支 `feat/my-toolkit-reorg` 上做；每个 Task 末尾提交。
- Windows 环境；路径用反斜杠/正斜杠均可（bash 工具）。

---

## File Structure

新建/修改文件职责：

- `launcher/__init__.py` — 包标记。
- `launcher/manifest.py` — 纯：解析 `tools/*/tool.toml` → `list[Tool]`。单测覆盖。
- `launcher/probe.py` — 纯：`port_open(port)` 探测端口。单测覆盖。
- `launcher/processes.py` — `ProcessRegistry`：start/stop/is_running，内存登记。
- `launcher/app.py` — Flask app：`/`(卡片)、`/launch/<slug>`、`/stop/<slug>`、`/status/<slug>`。
- `launcher/__main__.py` — 入口：起 `:5500` + 开浏览器。
- `launcher/templates/index.html` — 卡片仪表盘（含 JS 调 launch/stop/status）。
- `tests/launcher/test_manifest.py`、`tests/launcher/test_probe.py` — launcher 单测。
- `tools/pdf-ocr/tool.toml`、`tools/audio-player/tool.toml`、`tools/_template/tool.toml`、`tools/word2md/tool.toml`、`tools/dics/tool.toml` — 清单。
- `pyproject.toml`（顶层，新建）— 只管 launcher。
- `run.bat`、`run.sh`（新建）— 一键 `python -m launcher`。
- `README.md`（重写）— 工具箱总览。
- `tools/pdf-orch/pyproject.toml`（原根 pyproject `git mv` 而来，微调包发现）。

搬迁（`git mv`，保历史）：`pdfcover→tools/pdf-ocr/pdfcover`、`audioplayer→tools/audio-player`、`tests→tools/pdf-orch/tests`、`start_web.*`/`install_tesseract.bat`/`test_convert.py`/`pyproject.toml`/`README.md`→`tools/pdf-orch/`、样张 PDF→`tools/pdf-orch/samples/`。

---

## Task 1: 建分支 + 搬迁工具到 tools/（保历史）

**Files:**
- Move (git mv): `pdfcover` → `tools/pdf-ocr/pdfcover`；`audioplayer` → `tools/audio-player`；`tests`、`start_web.bat`、`start_web.sh`、`install_tesseract.bat`、`test_convert.py`、`pyproject.toml`、`README.md` → `tools/pdf-orch/`；`剑雅雅思10官方真题.pdf` → `tools/pdf-orch/samples/`
- Move (plain mv, gitignored): `coverdPDF` → `tools/pdf-orch/coverdPDF`；`audioplayer/books` → `tools/audio-player/books`

**Interfaces:** Produces the `tools/<slug>/` layout the rest of the plan depends on.

- [ ] **Step 1: 建分支**

```bash
cd /d/Users/luocj/pyProject/ky/pdfcover
git checkout -b feat/my-toolkit-reorg
```

- [ ] **Step 2: 建 tools 骨架并搬迁 pdf-orch（git mv，保历史）**

```bash
mkdir -p tools/pdf-ocr/samples
git mv pdfcover tools/pdf-ocr/pdfcover
git mv tests tools/pdf-ocr/tests
git mv start_web.bat start_web.sh install_tesseract.bat test_convert.py tools/pdf-ocr/
git mv pyproject.toml tools/pdf-ocr/pyproject.toml
git mv README.md tools/pdf-ocr/README.md
git mv 剑桥雅思10官方真题.pdf tools/pdf-orch/samples/剑桥雅思10官方真题.pdf
```

- [ ] **Step 3: 搬迁 audio-player（git mv + 数据 mv）**

```bash
git mv audioplayer tools/audio-player
# gitignore 的数据（git mv 不动未跟踪文件）跟着走：
mv audioplayer/books tools/audio-player/books 2>/dev/null
rm -rf audioplayer  # 清理残留的未跟踪日志等
```

- [ ] **Step 4: 搬迁 coverdPDF（gitignore 输出，普通 mv）**

```bash
mv coverdPDF tools/pdf-ocr/coverdPDF 2>/dev/null
```

- [ ] **Step 5: 验证 pdfcover 仍可跑 + 测试仍过**

```bash
cd tools/pdf-ocr
python -m pdfcover.web &  # 应在 :5000 起来；Ctrl+C 停
# 测试：
python -m pytest -q
cd ../..
```
Expected: web 起在 :5000；pytest 全过（导入 `from pdfcover import ...` 在 cwd=tools/pdf-orch 下成立）。

- [ ] **Step 6: 验证 audioplayer 仍可跑**

```bash
cd tools/audio-player
python dev_server.py 8123 &  # 起在 :8123；Ctrl+C 停
cd ../..
```
Expected: `:8123` 返回 200。

- [ ] **Step 7: 提交**

```bash
git add -A
git commit -m "refactor: 搬迁 pdfcover/audioplayer 到 tools/ 下（保历史）"
```

---

## Task 2: 写 tool.toml 清单 + _template

**Files:**
- Create: `tools/pdf-ocr/tool.toml`、`tools/audio-player/tool.toml`、`tools/_template/tool.toml`、`tools/word2md/tool.toml`、`tools/dics/tool.toml`

**Interfaces:** Produces `tools/*/tool.toml`，供 Task 3 的 `load_tools` 解析。

- [ ] **Step 1: pdf-ocr/tool.toml**

```toml
# tools/pdf-ocr/tool.toml
name = "PDF 影印→可搜索 OCR"
desc = "扫描版 PDF 用 OCR 转成可搜索、可选中文字的 PDF（Tesseract）"
category = "文档"
status = "ready"

[run]
cmd = ["python", "-m", "pdfcover.web"]
port = 5000
url = "http://127.0.0.1:5000"

[links]
live = ""
```

- [ ] **Step 2: audio-player/tool.toml**

```toml
# tools/audio-player/tool.toml
name = "音频播放器"
desc = "IELTS/ Collins/ 新概念 听力音频播放器（本地预览；线上见链接）"
category = "英语"
status = "ready"

[run]
cmd = ["python", "dev_server.py"]
port = 8000
url = "http://127.0.0.1:8000"

[links]
live = "http://47.108.230.162/script/"
```

- [ ] **Step 3: word2md / dics 占位（planned）**

```toml
# tools/word2md/tool.toml
name = "Word→Markdown"
desc = "Word 文档转 Markdown（占位，待实现）"
category = "文档"
status = "planned"
```
```toml
# tools/dics/tool.toml
name = "词典工具"
desc = "词典相关（占位，待实现）"
category = "英语"
status = "planned"
```

- [ ] **Step 4: _template/tool.toml（新工具模板）**

```toml
# tools/_template/tool.toml — 复制本目录改这个文件即可加新工具
name = "新工具"
desc = "一句话简介"
category = "分类"
status = "ready"

[run]
cmd = ["python", "main.py"]
port = 0
url = "http://127.0.0.1:0"

[links]
live = ""
```

- [ ] **Step 5: 提交**

```bash
git add tools/*/tool.toml
git commit -m "feat(toolkit): 加 tool.toml 清单 + _template + 占位"
```

---

## Task 3: launcher 清单解析（TDD）

**Files:**
- Create: `launcher/__init__.py`、`launcher/manifest.py`
- Test: `tests/launcher/test_manifest.py`

**Interfaces:**
- Produces: `Tool`（dataclass：slug,name,desc,category,status,cmd:list[str],port:int|None,url:str,live:str,dir:Path）、`load_tools(tools_dir:Path)->list[Tool]`。跳过 `_` 开头目录与无 tool.toml 的目录。

- [ ] **Step 1: 建包 + 写失败测试**

`launcher/__init__.py`：（空文件，包标记）
```python
```

`tests/launcher/test_manifest.py`：
```python
import textwrap
from pathlib import Path
from launcher.manifest import load_tools


def _make(tmp_path: Path, slug: str, body: str):
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
    assert [t.slug for t in tools] == ["dics", "pdf-ocr"]  # sorted by slug
    ready = tools[1]
    assert ready.status == "ready"
    assert ready.cmd == ["python", "-m", "pdfcover.web"]
    assert ready.port == 5000
    assert ready.url == "http://127.0.0.1:5000"
    planned = tools[0]
    assert planned.status == "planned"
    assert planned.cmd == [] and planned.port is None


def test_skip_underscore_and_no_manifest(tmp_path):
    _make(tmp_path, "_template", 'name = "t"\ndesc = ""\ncategory = ""\nstatus = "ready"\n')
    (tmp_path / "nope").mkdir()  # 无 tool.toml
    assert load_tools(tmp_path) == []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/launcher/test_manifest.py -q`
Expected: FAIL（`ModuleNotFoundError: launcher.manifest`）

- [ ] **Step 3: 实现 manifest.py**

```python
# launcher/manifest.py
"""解析 tools/*/tool.toml → Tool 列表（纯逻辑，可单测）。"""
from __future__ import annotations
import sys
from dataclasses import dataclass
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # Python 3.10
    import tomli as tomllib  # type: ignore


@dataclass
class Tool:
    slug: str
    name: str
    desc: str
    category: str
    status: str          # "ready" | "planned"
    cmd: list[str]
    port: int | None
    url: str
    live: str
    dir: Path


def load_tools(tools_dir: Path) -> list[Tool]:
    tools: list[Tool] = []
    if not tools_dir.is_dir():
        return tools
    for child in sorted(tools_dir.iterdir()):
        if not child.is_dir() or child.name.startswith("_"):
            continue
        toml = child / "tool.toml"
        if not toml.is_file():
            continue
        data = tomllib.loads(toml.read_text(encoding="utf-8"))
        run = data.get("run", {})
        links = data.get("links", {})
        tools.append(Tool(
            slug=child.name,
            name=data.get("name", child.name),
            desc=data.get("desc", ""),
            category=data.get("category", ""),
            status=data.get("status", "ready"),
            cmd=list(run.get("cmd", [])),
            port=run.get("port"),
            url=run.get("url", ""),
            live=links.get("live", ""),
            dir=child,
        ))
    return tools
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/launcher/test_manifest.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add launcher/__init__.py launcher/manifest.py tests/launcher/test_manifest.py
git commit -m "feat(launcher): tool.toml 清单解析（load_tools）+ 单测"
```

---

## Task 4: launcher 端口探测（TDD）

**Files:**
- Create: `launcher/probe.py`
- Test: `tests/launcher/test_probe.py`

**Interfaces:**
- Produces: `port_open(port:int, host:str="127.0.0.1", timeout:float=0.3)->bool`。

- [ ] **Step 1: 写失败测试**

`tests/launcher/test_probe.py`：
```python
import socket
from contextlib import closing
from launcher.probe import port_open


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_open_port_detected():
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    try:
        assert port_open(port) is True
    finally:
        srv.close()


def test_closed_port_not_detected():
    port = _free_port()  # 已关闭
    assert port_open(port) is False
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/launcher/test_probe.py -q`
Expected: FAIL（`ModuleNotFoundError: launcher.probe`）

- [ ] **Step 3: 实现 probe.py**

```python
# launcher/probe.py
"""探测 TCP 端口是否在监听。"""
import socket


def port_open(port: int, host: str = "127.0.0.1", timeout: float = 0.3) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/launcher/test_probe.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add launcher/probe.py tests/launcher/test_probe.py
git commit -m "feat(launcher): 端口探测 port_open + 单测"
```

---

## Task 5: launcher 进程管理 + Flask 面板

**Files:**
- Create: `launcher/processes.py`、`launcher/app.py`、`launcher/templates/index.html`

**Interfaces:**
- Consumes: `load_tools`、`port_open`。
- Produces: `create_app() -> Flask`（路由 `/`、`POST /launch/<slug>`、`POST /stop/<slug>`、`GET /status/<slug>`）、`ProcessRegistry`（start/stop/is_running）。

- [ ] **Step 1: processes.py（进程登记）**

```python
# launcher/processes.py
"""拉起/停止工具进程；内存登记（本地工具箱够用）。"""
from __future__ import annotations
import os
import signal
import subprocess
from .probe import port_open


class ProcessRegistry:
    def __init__(self) -> None:
        self._procs: dict[str, subprocess.Popen] = {}

    def start(self, slug: str, cmd: list[str], cwd, port: int | None = None) -> int:
        self.stop(slug)
        kwargs = {"cwd": str(cwd)}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        self._procs[slug] = subprocess.Popen(cmd, **kwargs)
        return self._procs[slug].pid

    def is_running(self, slug: str, port: int | None = None) -> bool:
        proc = self._procs.get(slug)
        alive = bool(proc and proc.poll() is None)
        if port is not None:
            return port_open(port)  # 以端口为准（兼容外部启动）
        return alive

    def stop(self, slug: str) -> bool:
        proc = self._procs.pop(slug, None)
        if not proc:
            return False
        if proc.poll() is None:
            try:
                if os.name == "nt":
                    proc.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                proc.kill()
        return True


registry = ProcessRegistry()
```

- [ ] **Step 2: app.py（Flask 路由）**

```python
# launcher/app.py
"""Flask 总入口面板。"""
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
            for _ in range(40):           # 最多等 ~10s
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
```

- [ ] **Step 3: templates/index.html（卡片仪表盘）**

```html
<!-- launcher/templates/index.html -->
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>my-toolkit</title>
  <style>
    body { font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
           background: #f5f5f7; margin: 0; padding: 24px; color: #1d1d1f; }
    h1 { font-size: 22px; margin: 0 0 4px; }
    .sub { color: #86868b; margin: 0 0 20px; }
    .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; }
    .card { background: #fff; border: 1px solid #eee; border-radius: 14px; padding: 16px; }
    .cat { font-size: 12px; color: #86868b; }
    .name { font-size: 17px; font-weight: 600; margin: 4px 0; }
    .desc { font-size: 13px; color: #555; min-height: 36px; }
    .row { display: flex; gap: 8px; margin-top: 12px; flex-wrap: wrap; align-items: center; }
    button { border: 1px solid #d2d2d7; background: #fff; border-radius: 10px;
             padding: 8px 14px; font-size: 14px; cursor: pointer; }
    button.primary { background: #3b82f6; color: #fff; border-color: #3b82f6; }
    button:disabled { opacity: .5; cursor: default; }
    .badge { font-size: 12px; padding: 2px 8px; border-radius: 8px; background: #e8f5e9; color: #2e7d32; }
    .badge.off { background: #f0f0f0; color: #86868b; }
    .badge.plan { background: #fff3e0; color: #ef6c00; }
    a { color: #3b82f6; text-decoration: none; font-size: 14px; }
    .planned { opacity: .6; }
  </style>
</head>
<body>
  <h1>🧰 my-toolkit</h1>
  <p class="sub">个人本地工具箱 · 点「启动」即拉起并在新页签打开</p>
  <div class="grid">
    {% for t in tools %}
    <div class="card {{ '' if t.status == 'ready' else 'planned' }}">
      <div class="cat">{{ t.category or '未分类' }}</div>
      <div class="name">{{ t.name }}</div>
      <div class="desc">{{ t.desc }}</div>
      {% if t.status != 'ready' %}
        <div class="row"><span class="badge plan">敬请期待</span></div>
      {% else %}
      <div class="row">
        <span class="badge {{ '' if statuses[t.slug] else 'off' }}" id="st-{{ t.slug }}">
          {{ '运行中' if statuses[t.slug] else '已停止' }}
        </span>
      </div>
      <div class="row">
        <button class="primary" onclick="launch('{{ t.slug }}','{{ t.url }}')">启动</button>
        <button onclick="stop('{{ t.slug }}')">停止</button>
        <a target="_blank" href="{{ t.url }}">打开</a>
        {% if t.live %}<a target="_blank" href="{{ t.live }}">线上</a>{% endif %}
      </div>
      {% endif %}
    </div>
    {% endfor %}
  </div>
<script>
async function launch(slug, url){
  const b = event.target; b.disabled = true; b.textContent = '启动中…';
  await fetch('/launch/'+slug,{method:'POST'});
  b.disabled = false; b.textContent = '启动';
  window.open(url, '_blank');
  refresh(slug);
}
async function stop(slug){ await fetch('/stop/'+slug,{method:'POST'}); refresh(slug); }
async function refresh(slug){
  const r = await fetch('/status/'+slug); const j = await r.json();
  const el = document.getElementById('st-'+slug);
  if(el){ el.textContent = j.running?'运行中':'已停止'; el.className = 'badge '+(j.running?'':'off'); }
}
</script>
</body>
</html>
```

- [ ] **Step 4: 确认 launcher 可导入（语法/路径）**

Run: `python -c "from launcher.app import create_app; create_app()"`
Expected: 无报错（返回 Flask app）。

- [ ] **Step 5: 提交**

```bash
git add launcher/processes.py launcher/app.py launcher/templates/index.html
git commit -m "feat(launcher): 进程管理 + Flask 面板(启动/打开/停止/状态)"
```

---

## Task 6: launcher 入口 + 顶层 pyproject + run 脚本

**Files:**
- Create: `launcher/__main__.py`、`pyproject.toml`（顶层）、`run.bat`、`run.sh`

**Interfaces:** Produces `python -m launcher`（:5500 + 开浏览器）。

- [ ] **Step 1: launcher/__main__.py**

```python
# launcher/__main__.py
import threading
import time
import webbrowser
from .app import create_app


def main():
    app = create_app()
    threading.Thread(
        target=lambda: (time.sleep(1.2), webbrowser.open("http://127.0.0.1:5500")),
        daemon=True,
    ).start()
    app.run(host="127.0.0.1", port=5500, debug=False)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 顶层 pyproject.toml（只管 launcher）**

```toml
# pyproject.toml（顶层）
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "my-toolkit-launcher"
version = "0.1.0"
description = "个人本地工具箱总入口面板"
requires-python = ">=3.10"
dependencies = [
    "flask>=3.0",
    "tomli>=2.0; python_version < '3.11'",
]

[tool.setuptools.packages.find]
include = ["launcher*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 3: run.bat / run.sh**

```bat
:: run.bat
@echo off
cd /d "%~dp0"
python -m launcher
pause
```
```bash
# run.sh
#!/bin/bash
cd "$(dirname "$0")"
python -m launcher
```

- [ ] **Step 4: 装依赖并冒烟启动**

```bash
pip install -e .
python -m launcher &   # 应在 :5500 起来并开浏览器；Ctrl+C 停
```
Expected: `:5500` 返回面板 HTML（含工具卡片）。

- [ ] **Step 5: 提交**

```bash
git add launcher/__main__.py pyproject.toml run.bat run.sh
git commit -m "feat(launcher): 入口 __main__ + 顶层 pyproject + run 脚本"
```

---

## Task 7: 顶层 README + 端到端验证

**Files:**
- Modify: `README.md`（顶层，重写为工具箱总览）

- [ ] **Step 1: 重写顶层 README.md**

```markdown
# 🧰 my-toolkit

个人本地开发/学习工具箱。一个 Flask 总入口面板，点工具即启动并跳转。

## 启动

```bash
pip install -e .          # 装 launcher 依赖（flask）
python -m launcher        # 或双击 run.bat / ./run.sh
```

浏览器自动打开 http://127.0.0.1:5500 ，点【启动】即可用对应工具。

## 内置工具

| 工具 | 说明 | 启动后 |
|---|---|---|
| PDF 影印→可搜索 OCR | 扫描版 PDF 用 OCR 转可搜索 PDF | http://127.0.0.1:5000 |
| 音频播放器 | IELTS/Collins/新概念 听力 | http://127.0.0.1:8000（另有线上：47.108.230.162/script/） |

（word2md、dics 为占位，待实现。）

## 加新工具

1. `cp -r tools/_template tools/<你的工具>`
2. 改 `tools/<你的工具>/tool.toml`（name/desc/cmd/port/url）
3. 把代码放进去
4. 刷新面板——自动出现，无需改 launcher。

## 目录

```
tools/<工具>/        各工具自包含（含 tool.toml 清单）
launcher/            Flask 总入口面板
docs/                设计/计划文档
```

各工具的详细说明见各自目录的 README。
```

- [ ] **Step 2: 端到端验证**

```bash
python -m launcher &
# 浏览器面板：
#  - pdf-ocr 卡片点【启动】→ :5000 可访问
#  - audio-player 卡片点【启动】→ :8000 可访问
#  - word2md/dics 显示「敬请期待」，无启动按钮
# git 历史可追：
git log --follow --oneline tools/pdf-orch/pdfcover/converter.py | head
# pdfcover 测试仍过：
( cd tools/pdf-ocr && python -m pytest -q )
# launcher 单测：
python -m pytest tests/launcher -q
```
Expected: 两工具点开即用；`git log --follow` 能看到搬迁前的历史；pytest 全过。

- [ ] **Step 3: 提交**

```bash
git add README.md
git commit -m "docs: 顶层 README 工具箱总览"
```

---

## Task 8: 合并 + 文件夹改名（my-toolkit）+ 可选 GitHub

**Files:** 无代码改动；OS 改名 + git。

- [ ] **Step 1: 合并到 main**

```bash
git checkout main
git merge --no-ff feat/my-toolkit-reorg -m "feat: 重组为 my-toolkit 工具箱（tools/ + launcher 总入口）"
```

- [ ] **Step 2: 改文件夹名 pdfcover → my-toolkit**

> ⚠️ 这会改项目路径。先**关闭 PyCharm / 本会话依赖的终端对该目录的占用**；命令从父目录执行。

```bash
cd /d/Users/luocj/pyProject/ky
mv pdfcover my-toolkit
cd my-toolkit
git status   # 确认 git 仍正常（文件夹改名不影响仓库）
```

- [ ] **Step 3（可选）：GitHub 仓改名 + 更新 remote**

GitHub 网页 Settings → Repository name → `my-toolkit`（旧 URL 自动跳转）。然后：

```bash
git remote set-url origin git@github.com:<user>/my-toolkit.git
git push -u origin main
```

- [ ] **Step 4: 最终验证**

在新路径下 `python -m launcher`，面板与两工具正常即完成。

---

## Self-Review 记录

- **Spec 覆盖**：目录结构(§3)→Task1；launcher(§4)→Task3-6；tool.toml(§5)→Task2；迁移/历史(§6)→Task1+8；文档(§7)→Task7；验证(§8)→Task7+8。全覆盖。
- **占位符扫描**：无 TBD/TODO；代码块均给出实际内容。
- **类型一致**：`Tool` 字段、`load_tools`/`port_open`/`ProcessRegistry.*` 在各 Task 间命名一致。
- **风险**：pdfcover 搬迁后 `python -m pdfcover.web`/pytest 需 cwd=tools/pdf-orch/（Task1 Step5 验证）；文件夹改名需先释放目录占用（Task8 Step2 警示）。
