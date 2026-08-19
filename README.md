# 🧰 my-toolkit

个人本地开发/学习工具箱。一个 Flask 总入口面板，点工具即启动并在新页签打开。

## 启动

```bash
pip install -e .          # 装 launcher 依赖（flask）
python -m launcher        # 或双击 run.bat / ./run.sh
```

浏览器自动打开 http://127.0.0.1:5500 ，点【启动】即可用对应工具。

## 内置工具

| 工具 | 说明 | 启动后地址 |
|---|---|---|
| PDF 影印→可搜索 OCR | 扫描版 PDF 用 OCR 转可搜索/可选中文字 PDF | http://127.0.0.1:5000 |
| 音频播放器 | IELTS / Collins / 新概念 听力（另有线上：http://47.108.230.162/script/ ） | http://127.0.0.1:8000 |
| Agent 学习路线 | 零基础转 Agent 开发学习地图 + 本地跟练代码 | http://127.0.0.1:7000 |
| 羽联数据 | BWF 世界排名/赛程抓取 → JSON → 发布羽圈 App（批处理，无网页） | — |
| 文本转语音 MP3 | 粘贴文本 → edge-tts 神经语音导出 MP3（默认存 IELTS 口语回答/音频） | http://127.0.0.1:8300 |

（word2md、dics 为占位，待实现。）

## 加新工具

1. 复制 `tools/_template/` → `tools/<你的工具>/`
2. 改 `tools/<你的工具>/tool.toml`（`name` / `desc` / `[run] cmd,port,url`）
3. 把代码放进该目录
4. 刷新面板——自动出现，**无需改 launcher**。

## 目录

```
tools/<工具>/      各工具自包含（含 tool.toml 清单 + 各自 README）
launcher/          Flask 总入口面板
tests/             launcher 单测
docs/              设计/计划文档（docs/superpowers/{specs,plans}）
```

各工具的详细说明见各自目录的 README（如 `tools/pdf-ocr/README.md`）。
