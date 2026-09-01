# B站双语字幕（bilibili-subtitles）

粘贴 B 站视频链接，读取视频自带或 AI 字幕轨，按时间轴生成适合边听边看的中英对照字幕，并下载为 Markdown 或 Excel。

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
3. 确认 English / 中文轨道。双语内容如果在同一条轨道里，两个选择框可选同一项。
4. 生成后直接在电脑的大字幕阅读页对照看，也可以搜索、调字号、复制 Markdown。
5. 下载 `.md` 或 `.xlsx`。Excel 内含标题、来源、真实时间值、冻结表头、筛选和自动换行。

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
- SRT、WebVTT，以及 B 站 `body/from/to/content` JSON 字幕结构。
- 两条中英文轨分段不一致：按时间重叠对齐；同一翻译覆盖多句英文时自动合并，减少重复。
- 单条双语轨：支持常见的“英文换行中文”“英文 | 中文”结构。
- 多 P 视频：链接带 `?p=N` 时读取指定 P；不带时取第 1 P。

## 当前边界

- 网页模式只提取字幕轨，不下载视频或音频；没有字幕轨时会明确提示。
- 命令行一键模式会在没有字幕轨时临时下载音频并调用 Whisper，结束后删除临时音频。
- 一键模式用 Google Translate / MyMemory 后端链补齐缺失语言（自动探测切换），结果属于机器翻译，需要抽查；MyMemory 对习语（如 over the moon）可能直译。
- 画面里烧录的字幕不会做 OCR；无字幕轨时的一键模式识别的是音频内容。
- 时间轴对齐依赖两条字幕自身的时间，极少数切分差异特别大的视频可能需要人工微调。
- B 站接口变化时先升级 `yt-dlp`：`python -m pip install -U yt-dlp`。

## 结构

| 文件 | 职责 |
|---|---|
| `app.py` | Flask 页面与读取/生成/下载 API；任务仅缓存在内存 |
| `extractor.py` | `yt-dlp` 字幕抓取、浏览器登录状态、错误提示 |
| `subtitle_core.py` | 字幕解析、语言识别、双语拆分、时间轴对齐、Markdown |
| `xlsx_export.py` | 标准 OOXML Excel 导出（无需额外 Excel 库） |
| `direct_generate.py` | 一条命令直接输出文件；无字幕时 Whisper + 机器翻译兜底 |
| `templates/index.html` / `static/*` | 电脑端双语阅读界面 |

离线单测在根目录 `tests/test_bilibili_subtitles.py`；测试不访问 B 站。
