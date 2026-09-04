# B站双语字幕（bilibili-subtitles）

粘贴 B 站视频链接，读取视频自带或 AI 字幕轨，按时间轴生成适合边听边看的中英对照字幕，并下载为 Markdown、Excel 或双语 SRT。视频没有字幕轨但 UP 主说英文时，可用语音识别（Whisper）转写英文再机器翻译中文。

## 使用

首次安装工具自己的依赖：

```bash
python -m pip install -r tools/bilibili-subtitles/requirements.txt
```

之后从工具箱总面板点「B站双语字幕」，或直接运行：

```bash
cd tools/bilibili-subtitles
python app.py
```

打开 http://127.0.0.1:8600 ：

1. 粘贴 `bilibili.com/video/...`、`b23.tv/...`，也可直接输入 BV 号。
2. 普通字幕先选「不读取登录状态」；如果提示登录后才有字幕，再选择本机已登录 B 站的 Edge / Chrome / Firefox。浏览器 Cookie 只交给本机 `yt-dlp` 使用，不保存到项目。
3. 有字幕轨时确认 English / 中文轨道（双语内容如果在同一条轨道里，两个选择框可选同一项）。
4. 没有字幕轨时（英文口播视频），点「识别英文语音并生成双语字幕」：后台下载临时音频（识别完自动删除，不下载视频）→ `faster-whisper small.en` 转写 → 机器翻译补中文，页面实时显示进度；需要先装 `requirements-whisper.txt`。
5. 生成后直接在电脑的大字幕阅读页对照看，也可以搜索、调字号、复制 Markdown。
6. 下载 `.md`、`.xlsx` 或双语 `.srt`（标准字幕格式，带时间戳，方便播放器加载或二次处理）。Excel 内含标题、来源、真实时间值、冻结表头、筛选和自动换行。
7. 阅读页可把字幕**转成 MP3 音频**：选英文/中文全文、语音（微软神经语音）、语速，后台分片合成后下载；复用「文本转语音 MP3」工具的 edge-tts 核心（见下方 tts_bridge）。

## 直接给链接生成文件（含无字幕视频兜底）

如果不需要网页操作，可安装语音识别依赖后直接执行：

```bash
python -m pip install -r tools/bilibili-subtitles/requirements-whisper.txt
python tools/bilibili-subtitles/direct_generate.py "https://www.bilibili.com/video/BV..." -o tools/bilibili-subtitles/outputs/BV...
```

处理顺序：优先使用视频字幕轨；没有字幕轨时下载临时音频，用 `faster-whisper small.en` 生成英文时间轴，再机器翻译补中文。最终只留下 `.md` 和 `.xlsx`，临时音频自动删除。机器识别/翻译会写进 Markdown 的生成说明，不冒充作者字幕。

机器翻译是自动切换的后端链：先 3 秒探测 Google Translate（可达则优先用，质量更好）；
不可达时直接使用 MyMemory（免 key）。MyMemory 单条限 500 字符会自动按句分片；
匿名额度有限，设置环境变量 `MYMEMORY_EMAIL` 可提额。有代理时设 `HTTPS_PROXY`
即可走回 Google 路径。

## 能处理什么

- B 站视频自带字幕和 B 站可访问的 AI 字幕。
- 无字幕轨的英文口播视频：网页和命令行都会下载临时音频，用 `faster-whisper small.en` 识别英文时间轴（只支持英文语音），再机器翻译中文。
- SRT、WebVTT，以及 B 站 `body/from/to/content` JSON 字幕结构。
- 两条中英文轨分段不一致：按时间重叠对齐；同一翻译覆盖多句英文时自动合并，减少重复。
- 单条双语轨：支持常见的“英文换行中文”“英文 | 中文”结构。
- 多 P 视频：链接带 `?p=N` 时读取指定 P；不带时取第 1 P。

## 当前边界

- 网页模式不下载视频；语音识别只临时下载音频，识别完自动删除，不落盘。
- 语音识别依赖是可选的：未装 `requirements-whisper.txt` 时网页会提示安装命令，其余功能不受影响。
- 语音识别任务在内存中运行，刷新页面会丢进度，需要重新识别；识别 + 翻译全程约几分钟（20 分钟视频约 8 分钟），请保持页面打开。
- 中文语音视频暂不支持自动转写（Whisper 模型用 `small.en`，仅英文）。
- 机器翻译用 Google Translate / MyMemory 后端链（自动探测切换），结果需要抽查；MyMemory 对习语（如 over the moon）可能直译。
- 「转 MP3」依赖兄弟工具 `tools/text2mp3/` 的 `tts_core.py`（模块互调只发生在核心逻辑层，两个网页应用保持独立）；需要安装 `tools/text2mp3/requirements.txt`（edge-tts）。缺依赖时页面给出安装提示，其余功能不受影响。
- 画面里烧录的字幕不会做 OCR；无字幕轨时识别的是音频内容。
- Excel 由纯标准库生成，采用 Excel 原生的 sharedStrings + theme 形态（预览窗格 / 手机端 / 微信 QQ 预览等轻量查看器也兼容；早期 inlineStr 版本在部分查看器里显示空白）。
- 时间轴对齐依赖两条字幕自身的时间，极少数切分差异特别大的视频可能需要人工微调。
- B 站接口变化时先升级 `yt-dlp`：`python -m pip install -U yt-dlp`。

## 结构

| 文件 | 职责 |
|---|---|
| `app.py` | Flask 页面与读取/生成/下载 API；语音识别后台任务与轮询；任务仅缓存在内存 |
| `extractor.py` | `yt-dlp` 字幕抓取、浏览器登录状态、错误提示 |
| `subtitle_core.py` | 字幕解析、语言识别、双语拆分、时间轴对齐、Markdown、SRT |
| `xlsx_export.py` | 标准 OOXML Excel 导出（无需额外 Excel 库） |
| `direct_generate.py` | 管线核心（音频下载 → Whisper 转写 → 翻译）；一条命令直接输出文件 |
| `tts_bridge.py` | 引用 text2mp3 的 tts_core：行→朗读文本、分片合成、拼接 MP3 |
| `templates/index.html` / `static/*` | 电脑端双语阅读界面与语音识别进度 |

离线单测在根目录 `tests/test_bilibili_subtitles.py`；测试不访问 B 站。
