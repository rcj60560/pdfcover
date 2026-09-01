# my-toolkit 工具箱 · 项目导读（2026-09-01）

> 给后续会话（人或 AI）的快速上手文档：这个仓库是什么、怎么跑、怎么加东西。
> 历史细节见文末「变更记录」。

## 是什么

个人本地开发/学习工具箱：**一个 Flask 总入口面板，点工具即启动并在新页签打开**。
由原 `pdfcover` 仓库重组而来。核心理念：**工具自包含、清单驱动**——每个工具一个目录，
放一个 `tool.toml` 声明名称/命令/端口，面板自动发现，**加新工具不改 launcher**。

## 怎么跑

```bash
pip install -e .          # 装 launcher 依赖（flask）
python -m launcher        # 或双击 run.bat / ./run.sh → 自动开浏览器 http://127.0.0.1:5500
```

## 目录结构

```
launcher/              Flask 面板（:5500）：manifest.py 解析 toml / probe.py 探活 / processes.py 进程管理
tools/<工具>/          各工具自包含：tool.toml 清单 + 代码 + 各自 README
tools/_template/       新工具模板（复制即用）
tests/                 根级单测（launcher + 各工具纯逻辑），pytest 直接跑
docs/                  本文档 + superpowers/{specs,plans} 设计/计划文档
```

## 当前工具

| slug | 名称 | 端口 | 启动 | 说明 |
|---|---|---|---|---|
| pdf-ocr | PDF 影印→可搜索 OCR | 5000 | `python -m pdfcover.web` | Tesseract OCR，工具内有独立 pyproject |
| audio-player | 音频播放器 | 8000 | `python dev_server.py` | IELTS/Collins/新概念听力；线上 http://47.108.230.162/script/ |
| agent-learning | Agent 学习路线 | 7000 | `python dev_server.py` | 学习地图 + 跟练代码 |
| bwf-data | 羽联数据 | — | `python run_all.py` | BWF 排名/赛程抓取→发布（批处理，无网页） |
| text2mp3 | 文本转语音 MP3 | 8300 | `python app.py` | 粘贴文本→edge-tts→MP3（新一代 Ava/Emma 语音 + 音调微调），默认存 IELTS 笔记库口语回答/音频；另有 `tts_cli.py` 供自动化 |
| speaking-player | 口语跟读播放器 | 8400 | `python dev_server.py` | MP3+timeline json 卡拉OK逐词高亮跟读；sync_speaking.py 一键上服务器 |
| bilibili-subtitles | B站双语字幕 | 8600 | `python app.py` | 提取 B 站字幕轨、按时间轴生成中英对照，导出 Markdown / Excel |
| word2md / dics | （占位） | — | — | planned，面板置灰 |

## 加新工具（3 步，无需改 launcher）

1. 复制 `tools/_template/` → `tools/<你的工具>/`
2. 改 `tool.toml`：`name` / `desc` / `category` / `[run] cmd,port,url`（端口避开已用的 5000/5500/7000/8000/8300/8400）
3. 代码丢进去；纯逻辑抽 `*_core.py` 之类，测试放根 `tests/test_<工具名>.py`

刷新面板自动出现。

## 约定（AI 会话开发前速读）

- **端口分配**：面板 5500；工具 5000 / 7000 / 8000 / 8300 / 8400 / 8500 / 8600 已占，新工具挑没用的。
- **测试**：根 `pytest` 一把跑全部；根 tests/ 导入工具代码用 `sys.path.insert(0, .../tools/<工具>)`（见 `tests/test_bwf_preview.py`、`tests/test_text2mp3.py`）。跨工具依赖网络/重进程的不进单测。
- **TDD/流程**：本仓库用 superpowers 工作流，设计/计划文档在 `docs/superpowers/{specs,plans}`，命名 `YYYY-MM-DD-<主题>-{design,plan}.md`。
- **工具自包含**：web 工具两种风格都行——stdlib `http.server`（audio-player）或 Flask（text2mp3、pdf-ocr web）；依赖多就给工具配 `requirements.txt` 或独立 pyproject。
- **本地个人路径**：输出目录、配置等写默认值即可（如 text2mp3 的 `DEFAULT_OUT_DIR` 指 IELTS Obsidian 库），运行时配置类文件 gitignore（见 `tools/text2mp3/config.json`）。
- **Python**：3.12，Windows 环境；`explorer /select,` 可用于定位文件。

## 关联项目

- **IELTS Obsidian 库**（`D:\Users\luocj\Obsidian\IELTS\IELTS`）：text2mp3 默认输出目的地；口语话题笔记工作流（素材.md → 7 分回答 → MP3 跟读）。

## 变更记录

- **2026-09-01**：新增 `bilibili-subtitles`（B站字幕提取→中英时间轴对齐→Markdown/Excel，:8600）。
- **2026-08-19**：新增 `speaking-player`（卡拉OK 跟读播放器，:8400）；text2mp3 升级为 MP3+timeline json 双落地。
- **2026-08-19**：新增 `text2mp3`（文本→edge-tts→MP3，:8300），根 README 工具表补全（agent-learning、bwf-data），本文档改为「项目导读」并新增 AI 会话约定章节。
- **2026-07-31**：pdfcover/audioplayer `git mv` 搬入 `tools/`（历史保留）；launcher（manifest+probe+processes+面板）TDD 完成；顶层 README/pyproject/run 脚本就位；测试全绿（launcher 4 + pdfcover 54 + audioplayer 19）。

## 待办 / 已知

- 文件夹改名 `pdfcover` → `my-toolkit`：需关闭 IDE/会话后资源管理器改（会话占用时报 `Device or resource busy`）。
- audio-player issue 12 编号错位（Test5-8）待修。
- `sync_audio_library.py` 源路径失效（`D:\夸克下载` 已重组），需更新 `DEFAULT_SOURCES`。
