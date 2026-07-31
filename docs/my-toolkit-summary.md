# my-toolkit 工具箱 · 现状总结（2026-07-31）

## 是什么
个人本地工具箱：一个 Flask 总入口面板，点工具即启动并在新页签打开。由原 `pdfcover` 仓库重组而来。

## 结构
- `launcher/` — Flask 面板（:5500）。`python -m launcher`（或 `run.bat` / `run.sh`）启动，自动开浏览器。
- `tools/<工具>/tool.toml` — 每个工具自包含，清单驱动（`name`/`desc`/`[run] cmd,port,url`/`[links] live`）。面板自动发现，**加新工具不改 launcher**。
- `tools/_template/` — 新工具模板（复制即用）。
- `docs/` — 设计/计划文档 + 本总结。

## 当前工具
| 工具 | 状态 | 启动 |
|---|---|---|
| pdf-ocr（原 pdfcover） | ready | `python -m pdfcover.web` → :5000 |
| audio-player（原 audioplayer） | ready | `python dev_server.py` → :8000（线上 http://47.108.230.162/script/ ） |
| word2md / dics | planned | 占位（面板置灰） |

## 加新工具
复制 `tools/_template/` → `tools/<新名>/` → 改 `tool.toml` → 丢代码进去。刷新面板自动出现。

## 已完成（2026-07-31，merge commit `95957f7`）
- pdfcover / audioplayer 经 `git mv` 搬入 `tools/`，**历史保留**（`git log --follow` 可追到搬迁前提交）
- launcher（manifest 解析 + 端口探测 + 进程管理 + Flask 面板）TDD，单测 4 个
- 顶层 `README.md` / `pyproject.toml` / `run.bat` / `run.sh`；端到端验证通过；合并到 `main`
- 测试全绿：launcher 4 + pdfcover 54 + audioplayer 19

## 待办 / 已知
- **文件夹改名 `pdfcover` → `my-toolkit`**：需关闭 IDE/Claude 会话后在资源管理器改（会话进行中文件夹被占用，改不了，已实测 `Device or resource busy`）。git 不受影响。改名后可顺手删残留的空 `audioplayer/`（仅 `.claude`）。
- **issue 12 编号错位**（Test5-8）：待修。
- **`sync_audio_library.py` 源路径失效**：`D:\夸克下载` 已重组（`听力音频` / `剑雅19-21` → 现在是 `剑雅雅思1-21` 等一堆新资料），需更新 `DEFAULT_SOURCES` 才能重建本地剑雅音频。服务器上的剑15–21 仍在。
- `pdfcover.egg-info` / `my_toolkit_launcher.egg-info` 为 `pip install -e .` 生成物，已 gitignore。
