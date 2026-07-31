# my-toolkit 工具箱重组设计

- 日期：2026-07-31
- 状态：待评审
- 范围：把当前 `pdfcover` 仓库重组为个人本地工具箱 `my-toolkit`，加统一入口面板，结构清晰、可扩展、保留 git 历史。

## 1. 背景与目标

仓库最早是单个 PDF-OCR 工具（`pdfcover` 包），后来又长出了音频播放器（`audioplayer`），并预留了 `word2Md`、`dics` 等空占位。问题：目录杂、无统一入口、新工具没有固定套路。

目标：

- 改名为 `my-toolkit`，定位为「个人本地开发/学习工具箱」。
- 提供一个 Flask 总入口面板：点工具 → 后台拉起它的 web 服务并跳转过去（"点开就用"）。
- 清晰的 `tools/<工具>/` 统一布局；加新工具 = 建子目录 + 清单，**不改入口代码**。
- 全程保留 git 历史（`git mv`）与现有文档。

非目标：不改各工具内部实现；不做多用户/线上托管；不重写 git 历史。

## 2. 范围（含/不含）

纳入的工具（面板入口）：

| 工具 | 来源 | 状态 |
|---|---|---|
| PDF 影印→可搜索 OCR | 原 `pdfcover/` 包 + web + tests + 脚本 | 可用 |
| 音频播放器 | 原 `audioplayer/` | 可用（本地 + 已部署服务器） |
| word2md | 原空占位 `word2Md/` | planned（占位，面板置灰） |
| dics | 原空占位 `dics/` | planned（占位，面板置灰） |

数据/输出随工具走，且 gitignore 的不进 git：`coverdPDF/`(1.5G OCR 产物)→`tools/pdf-ocr/`；`audioplayer/books/`(2.8G 音频)→`tools/audio-player/`；`pdfcover.egg-info/`、缓存、日志为生成物，忽略。

工作流/配置原样留顶层：`.gitignore`、`.claude/`、`.agents/`、`.superpowers/`、`docs/`。

## 3. 目标目录结构

```
my-toolkit/                              ← 文件夹改名(pdfcover→my-toolkit)；git 历史不动
├── README.md                            ← 重写：工具箱总览 + 启动方式 + 工具清单
├── run.bat / run.sh                     ← 一键启动面板：python -m launcher
├── pyproject.toml                       ← 顶层：只管 launcher（依赖 flask）
├── launcher/                            ← Flask 总入口面板
│   ├── __init__.py
│   ├── __main__.py                      ← python -m launcher → :5500，自动开浏览器
│   ├── app.py                           ← 扫描 tools/*/tool.toml；启动/打开/停止/状态
│   └── templates/index.html             ← 工具卡片页
├── tools/
│   ├── pdf-ocr/                         ← git mv 自原 pdfcover 相关文件
│   │   ├── tool.toml
│   │   ├── pdfcover/                    ← 包(含 web/)，原样
│   │   ├── tests/  start_web.bat  start_web.sh
│   │   ├── install_tesseract.bat  test_convert.py
│   │   ├── pyproject.toml               ← pdfcover 自己的打包，随工具搬入
│   │   ├── README.md                    ← pdfcover 原说明
│   │   ├── coverdPDF/                   ← 输出目录(gitignore)，本地数据跟着走
│   │   └── samples/剑桥雅思10官方真题.pdf ← 79M 样张
│   ├── audio-player/                    ← git mv 自 audioplayer/
│   │   ├── tool.toml
│   │   ├── (app.js core.js index.html style.css dev_server.py sync_audio_library.py
│   │   │   start_server.bat package.json nginx.conf.example README.md tests/)
│   │   └── books/                       ← 2.8G 音频(gitignore)
│   ├── word2md/  dics/                  ← planned 占位（仅 tool.toml，无 run）
│   └── _template/                       ← 新工具模板（含 tool.toml 样例）
├── docs/                                ← 原 docs/superpowers 设计/计划文档全保留
└── .gitignore .claude/ .agents/ .superpowers/   ← 工作流配置原样留
```

## 4. Launcher（Flask 面板）设计

- 入口：`python -m launcher`（或 `run.bat`/`run.sh`）→ Flask 起 `127.0.0.1:5500`，自动开浏览器。
- 发现：启动时扫描 `tools/*/tool.toml`，解析成工具列表。
- 面板（`templates/index.html`）：每个工具一张卡片，显示 `name`、`desc`（即功能介绍）、`category`、状态、按钮。
- 卡片按钮：
  - 【启动】`POST /launch/<tool>` → 以 `cwd=工具目录` 执行 `[run].cmd`（`subprocess.Popen`，新进程组/独立），登记 PID+端口；轮询直到端口可达，返回 `[run].url`。
  - 【打开】直链 `[run].url`（如 `:5000` / `:8000`）。
  - 【停止】`POST /stop/<tool>` → 终止登记的 PID（含子进程）。
  - 【线上】当 `[links].live` 非空时显示，直跳线上地址（音频播放器 → `http://47.108.230.162/script/`）。
- 状态：探测 `[run].port` 是否响应 → running / stopped。
- planned 工具（无 `[run]`）：卡片置灰，显示「敬请期待」，无启动按钮。
- 进程登记：内存 dict `{tool: {pid, port, url}}`，不持久化（本地工具箱够用；重启 launcher 后状态以端口探测为准）。

## 5. `tool.toml` 清单格式

```toml
name = "PDF 影印→可搜索 OCR"
desc = "扫描版 PDF 用 OCR 转成可搜索、可选中文字的 PDF"
category = "文档"
status = "ready"        # ready | planned

[run]                    # planned 工具省略整段
cmd = ["python", "-m", "pdfcover.web"]
port = 5000
url  = "http://127.0.0.1:5000"

[links]
live = ""               # 可选，线上地址
```

各工具清单：

- **pdf-ocr**：cmd=`["python","-m","pdfcover.web"]`, port=5000, url=`:5000`。
- **audio-player**：cmd=`["python","dev_server.py"]`, port=8000, url=`:8000`, links.live=`http://47.108.230.162/script/`。
- **word2md / dics**：`status="planned"`，无 `[run]`。

可扩展性：新工具 = `cp -r tools/_template tools/<新名>` → 改 `tool.toml` → 丢代码进去；面板自动发现，不改 launcher。

## 6. 迁移与历史保留

**关键认知**：文件夹改名与 git 历史无关——git 在 `.git/`，按仓库根跟踪文件，改磁盘目录名历史一字不变。仓库内搬迁用 `git mv` 保留历史。

步骤（在新分支上执行，全程可 `git reset` 回滚）：

1. **改名**：OS 把 `pdfcover` 目录改名为 `my-toolkit`（git 不受影响）。
2. **`git mv` 搬工具**（保历史，`git log --follow` 可追）：
   - `git mv pdfcover tools/pdf-ocr/pdfcover`
   - `git mv audioplayer tools/audio-player`
   - `git mv tests tools/pdf-ocr/tests`
   - `git mv start_web.bat start_web.sh install_tesseract.bat test_convert.py tools/pdf-ocr/`
   - `git mv pyproject.toml tools/pdf-ocr/pyproject.toml`
   - `git mv README.md tools/pdf-ocr/README.md`（pdfcover 原说明跟工具走）
   - `git mv 剑桥雅思10官方真题.pdf tools/pdf-ocr/samples/剑桥雅思10官方真题.pdf`（先 `mkdir -p tools/pdf-ocr/samples`）
   - `docs/` 保留在顶层。
3. **gitignore 数据**（无历史问题，普通移动）：`coverdPDF/`→`tools/pdf-ocr/coverdPDF/`；`books/` 随 audioplayer 走。
4. **路径修正**：
   - pdfcover 的 `pyproject.toml`（已在 `tools/pdf-orch/`）包发现仍找 `pdfcover/`；`python -m pdfcover.web` 与 pytest 均在 `tools/pdf-orch/` 下运行。
   - launcher 用 `cwd=工具目录` 启动各工具，命令仍用相对形式。
   - 顶层新增 `pyproject.toml`（仅 launcher，依赖 `flask`）。
5. **GitHub**：仓库改名 `pdfcover`→`my-toolkit`（可选，Settings 改名带旧 URL 跳转），`git remote set-url origin <新地址>`。
6. **可选瘦身**：79M 样张已在 git 历史中；如不想再跟踪可 `git rm --cached tools/pdf-orch/samples/*.pdf` + 改 `.gitignore`（不重写历史）。

## 7. 文档与功能介绍

- 顶层 `README.md`（重写）：工具箱简介、`python -m launcher` 启动方式、工具清单（每个一句话）。
- 各工具保留各自 `README.md`（pdfcover、audio-player）。
- **面板卡片直接显示 `tool.toml` 的 `desc` = 你要的"每个需求的功能介绍"**。
- `docs/`（含 `docs/superpowers/{specs,plans}` 的既有设计/计划文档）全保留。

## 8. 验证

- `python -m launcher` 打开面板，pdf-ocr 与 audio-player 能【启动】→【打开】正常使用；planned 卡片置灰。
- `git log --follow tools/pdf-orch/pdfcover/converter.py` 等能追到搬迁前的历史。
- 在 `tools/pdf-orch/` 下 `pytest` 仍通过；`python -m pdfcover.web` 仍起 `:5000`。
- audio-player 部署（47.108.230.162）不受影响（只是本地目录改名/搬迁）。
- 加一个 `_template` 复制的假工具，确认面板自动列出。

## 9. 开放默认（评审时确认）

- `coverdPDF/` → `tools/pdf-orch/coverdPDF/`（随工具，gitignore）。
- 包含 `tools/_template/` 模板。
- `word2md/`、`dics/` 作为 `planned` 占位（面板置灰）。
- 双 pyproject：顶层（launcher）+ `tools/pdf-orch/`（pdfcover）。

## 10. 风险与回滚

- 唯一需小心处：pdfcover 的打包/运行路径。搬入 `tools/pdf-orch/` 后必须验证 `python -m pdfcover.web` 与 pytest 仍工作。
- 全程在单独分支，`git mv` 可逆；任何步骤出问题可 `git reset` 回退，文件夹改名也可改回。
