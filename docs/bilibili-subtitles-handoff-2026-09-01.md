# B站双语字幕模块 · 开发交接（2026-09-01）

> 目的：让后续 AI 不需要重新摸项目，能直接从当前状态继续生成首个真实产物并收尾。

## 用户目标

用户在手机上播放 B 站视频，在电脑上阅读带时间轴的中英对照内容；最终产物需要 Markdown 和 Excel。

本轮用户给出的首个目标视频：

- URL：`https://www.bilibili.com/video/BV1C1t86wEM3/?spm_id_from=333.1007.top_right_bar_window_history.content.click`
- 识别到的标题主题：`Vocabulary in Use Advanced · Unit 14`（全英文教学）
- 时长：约 `20:09`
- 无登录状态读取结果：没有可提取的原生/AI 字幕轨
- 因此该视频必须走：临时音频 → Whisper 英文识别 → 中文机器翻译 → MD/XLSX
- **当前尚未对该视频跑完 Whisper，也尚未生成最终文件。**

## 已完成

### 1. 新工具已经接入 my-toolkit

- 目录：`tools/bilibili-subtitles/`
- 清单：`tool.toml`
- 端口：`8600`
- 工具箱面板会自动发现，无需修改 launcher。
- 根 `README.md` 与 `docs/my-toolkit-summary.md` 已登记新工具。

### 2. 网页字幕轨模式

入口：

```powershell
cd tools/bilibili-subtitles
python app.py
```

已实现：

- 支持 B 站视频页、`b23.tv`、BV/av 号，拒绝非 B 站 URL。
- 通过 `yt-dlp` 获取视频自带/AI 字幕；不下载视频。
- 可选无登录、Edge、Chrome、Firefox 浏览器登录状态。
- SRT、WebVTT、B站 JSON 字幕解析。
- 字幕内容语言识别；同轨中英双语拆分。
- 两条中英文轨按时间重叠对齐；同一翻译跨多句时合并，减少重复。
- 电脑阅读页：双语卡片、时间戳、搜索、字号调整、复制 Markdown。
- 下载 Markdown / Excel。
- 任务只缓存在内存，不保存 Cookie 或字幕中间数据。

主要文件：

| 文件 | 职责 |
|---|---|
| `app.py` | Flask 页面/API、内存任务、下载接口 |
| `extractor.py` | yt-dlp 获取字幕、浏览器 Cookie 选项、友好错误 |
| `subtitle_core.py` | 解析、识别语言、双语拆分、对齐、Markdown |
| `xlsx_export.py` | 纯标准库生成 OOXML `.xlsx` |
| `templates/index.html`、`static/*` | 阅读界面 |

Excel 已实现：标题和来源、真实时间数值、冻结前三行、筛选、自动换行、列宽、交替行底色；无需 `openpyxl`。

### 3. “链接进、产物出”一键模式

入口：`tools/bilibili-subtitles/direct_generate.py`

逻辑：

1. 优先尝试原生字幕轨。
2. 无字幕轨时，用 yt-dlp 下载临时最佳音频。
3. 用 `faster-whisper small.en` 在 CPU/int8 上识别英文时间轴。
4. 合并过碎的 Whisper 段，形成适合阅读的字幕块。
5. 用 `deep-translator` 的 GoogleTranslator 补齐中文（或缺失的英文）。
6. 写出 `.md` / `.xlsx`，临时目录退出时自动删除音频。
7. Markdown 会注明 Whisper/机器翻译方法，不冒充作者原生字幕。

可选依赖文件：`requirements-whisper.txt`。

## 本机/依赖状态

- Python：`3.12.10`
- Flask：已安装（`3.1.3`）
- yt-dlp：本轮已安装（`2026.8.19`）
- `faster-whisper`：**未安装**
- `deep-translator`：**未安装**
- `ffmpeg`：系统 PATH 未发现；一键脚本选择 faster-whisper/PyAV 路径，不依赖系统 ffmpeg
- 本地 Flask 服务已停止，不留后台进程
- 当前会话没有可控浏览器实例，因此没有完成真实截图视觉 QA；Flask API 已通过测试客户端验证

## 测试状态

测试文件：`tests/test_bilibili_subtitles.py`

覆盖：

- URL 白名单
- SRT/VTT/B站 JSON 解析
- 短双语轨语言识别
- 双语单轨拆分
- 跨轨对齐、未匹配字幕、重复翻译合并
- Markdown 结构
- XLSX ZIP/XML、冻结窗格、筛选、真实时间值
- Flask 生成预览及 MD/XLSX 下载接口
- launcher 自动发现
- Whisper 字幕块合并及翻译回填纯逻辑

本轮记录：

- 加入一键脚本前，全仓：`57 passed`
- 加入一键脚本后，本模块：`13 passed`
- 提交前最终全仓回归：`58 passed in 1.36s`

## 下一步（按顺序执行）

### 1. 安装 Whisper/翻译依赖

```powershell
python -m pip install -r tools/bilibili-subtitles/requirements-whisper.txt
```

注意：首次 Whisper 运行还会从 Hugging Face 下载 `small.en` 模型（数百 MB），CPU 处理 20 分钟视频需要等待一段时间。

### 2. 生成本次目标视频产物

```powershell
python tools/bilibili-subtitles/direct_generate.py "https://www.bilibili.com/video/BV1C1t86wEM3/" -o "tools/bilibili-subtitles/outputs/BV1C1t86wEM3"
```

预期输出：

```text
tools/bilibili-subtitles/outputs/BV1C1t86wEM3/<视频标题>-双语字幕.md
tools/bilibili-subtitles/outputs/BV1C1t86wEM3/<视频标题>-双语字幕.xlsx
```

`outputs/` 已在 `.gitignore`，产物不会误入 Git。

### 3. 做内容质量抽查

- 开头、中段、结尾各抽查 3–5 条。
- 重点检查本课专业词汇是否被 Whisper 错听。
- 检查字幕时间是否单调递增、有没有长段重复/幻觉。
- 检查中文是否漏译、翻译接口是否返回英文原文。
- 若 `small.en` 准确度不够，可改用 `--whisper-model medium.en`（更慢、模型更大）。

### 4. 做产物视觉检查

- Markdown：用常用编辑器打开，确认中英块和时间戳易读。
- Excel：确认标题/来源可见，表头冻结，D/E 长文本不截断，筛选正常。
- 如有可控浏览器，再对 `http://127.0.0.1:8600` 做桌面和窄屏截图 QA。

### 5. 回归

```powershell
python -m pytest -q
node --check tools/bilibili-subtitles/static/app.js
git diff --check
```

## 已知风险 / 待改进

- `deep-translator` 的 Google 路径无需 API Key，但依赖外部网页服务，可能限流或变化；脚本已有小批次与三次重试，但尚未真实跑满本视频。
- 一键 Whisper 路径目前只有离线纯逻辑测试，尚未做真实 20 分钟端到端验证。
- 网页模式和一键模式暂时是两个入口；网页遇到“无字幕轨”不会自动启动 Whisper。
- Excel 当前记录标题和来源 URL，但没有单独的“生成方法”元数据行；Markdown 有生成说明。
- B 站未登录时“没有字幕轨”和“登录后才展示字幕”有时难以区分；若用户明确允许，可尝试 `--browser edge`（或 chrome/firefox）。
- 机器翻译用于学习对照，不能视为出版级翻译。

## Git 范围提醒

提交时只包含本模块和相关文档/测试。仓库已有未跟踪目录：

- `.claude/`
- `audioplayer/`

它们不是本轮改动，**不要 stage、不要删除**。
