# B站双语字幕（bilibili-subtitles）

粘贴 B 站视频链接，拉取英文原文（字幕轨优先，无字幕轨时 Whisper 语音识别），配合词典整段精翻 + 一键排版，生成带时间轴的中英对照字幕 md。页面为「欧路词典精翻」流程专用，不再走机器翻译。

## 使用

首次安装工具自己的依赖（语音识别还需 `requirements-whisper.txt`）：

```bash
python -m pip install -r tools/bilibili-subtitles/requirements.txt
python -m pip install -r tools/bilibili-subtitles/requirements-whisper.txt
```

之后从工具箱总面板点「B站双语字幕」，或直接运行：

```bash
cd tools/bilibili-subtitles
python app.py
```

打开 http://127.0.0.1:8600 ，整个页面就是一条动线：

1. 粘贴 `bilibili.com/video/...`、`b23.tv/...` 或 BV 号，点「拉取英文」——读取视频信息后自动继续：
   有字幕轨就用英文轨生成；没有就下载临时音频（识别完自动删除，不下载视频）→
   `faster-whisper small.en` 转写（**仅英文，跳过机翻**），页面实时显示进度。
2. 普通视频先选「不读取登录状态」；如果提示登录后才有内容，再选择本机已登录 B 站的
   Edge / Chrome / Firefox。浏览器 Cookie 只交给本机 `yt-dlp` 使用，不保存到项目。
3. 完成后自动进入阅读区：点「📋 复制英文全文」得到不换行英文整段，丢给词典整段翻译。
4. 词典返回的整段中文粘到右侧「词典中文粘贴区」，点「🤖 一键排版」——本机无头调用
   `claude` 按字幕块断句点切分对齐回填（详见下方「词典精翻排版」）。一键失败时用
   「保存，交给 Claude 排版」+「⟳ 应用排版结果」走对话兜底。
5. 「下载 Markdown」即为最终双语稿（文件名 = 视频标题-双语字幕.md），放进对应书目文件夹，
   再到 subtitle-viewer `sync_subtitles.py` 上公网。
6. 页面右上角「停止服务」可彻底退出本地进程：关闭网页标签并不会停止终端里的程序，不用时点它退出。

> 已从页面精简掉的能力（后端接口与 CLI 仍保留）：中英轨道手动选择、机器翻译/重试翻译、
> Excel / SRT 导出、字幕转 MP3。需要时走 `direct_generate.py` 或恢复历史版本。

## 直接给链接生成文件（含无字幕视频兜底）

如果不需要网页操作，可安装语音识别依赖后直接执行：

```bash
python -m pip install -r tools/bilibili-subtitles/requirements-whisper.txt
python tools/bilibili-subtitles/direct_generate.py "https://www.bilibili.com/video/BV..." -o tools/bilibili-subtitles/outputs/BV...
```

处理顺序：优先使用视频字幕轨；没有字幕轨时复用本地转写，或下载临时音频，用 `faster-whisper small.en` 生成英文时间轴，再机器翻译补中文。输出 `.md` 和 `.xlsx`，转写与成功译文另存本地缓存，临时音频自动删除。机器识别/翻译会写进 Markdown 的生成说明，不冒充作者字幕。加 `--no-translate` 则跳过机翻仅出英文（词典精翻流程第一步，见下节）。

机器翻译先检查所有后端的缓存，再尝试 Google Translate → MyMemory（免 key）。
Google 使用网页翻译端点，并非 Google Cloud Translation API；可设置 `HTTPS_PROXY`。
请求的连接超时为 5 秒、读取超时为 20 秒。网络故障/服务端 5xx 最多尝试 3 次；
重试耗尽后该后端冷却 60 秒。HTTP 429 按 `Retry-After`（支持秒数或 HTTP 日期）
冷却，缺失时默认 60 秒，随后切换后端；无效输入不反复重试。

同一缓存目录下的网页、CLI 和多个视频共用请求节奏：Google 请求起点至少间隔 1 秒，
MyMemory 至少间隔 0.5 秒。这是保守默认值，不代表服务方承诺不会限流。
MyMemory 使用 HTTPS，单次按 UTF-8 **字节**限制切分（采用 480 字节余量，接口上限 500 字节）。
根据[官方额度说明](https://mymemory.translated.net/doc/usagelimits.php)，匿名为每天 5,000 字符，
提供可联系的有效邮箱后为每天 50,000 字符；额度耗尽时暂停该邮箱对应后端一小时，
防止每次重试继续请求，恢复时间仍以服务方为准。设置 `MYMEMORY_EMAIL` 后需重新启动进程。
页面右上角显示邮箱是否已配置，不显示具体地址，也不代表已向服务方验证额度。

### 翻译失败、刷新或重启后如何继续

- **本页任务仍在**：点「重试翻译」，只补缺失的语言；已经成功的中文仍能阅读、下载。
- **刷新页面或重启服务**：重新输入相同视频链接，读取后再点识别按钮。相同链接、分 P、
  模型和识别提示会复用已完成的转写，日志显示「复用本地转写」，不重下音频、不重跑 Whisper；
  翻译阶段复用成功分片。CLI 重新运行原命令也会复用这些缓存。
- **识别尚未完成就退出**：下次仍需重新识别；识别缓存仅在完整识别成功后写入。
- **字幕轨模式**：网页会重新读取并对齐已有字幕轨，本身不调用机器翻译；CLI 一键模式需要补译时可复用翻译缓存。
- 成功译文逐分片保存。即使同一条长字幕的后续分片失败，前面分片也不会在重试时重复请求。
- 本地缓存默认在 `outputs/.cache/translation.sqlite3`，包含转写文本、译文和后端冷却时间，
  不保存浏览器 Cookie 或邮箱明文，也不提交 Git。可用 `BILIBILI_CACHE_DIR` 指定其他目录；
  网页和 CLI 要共享限流/缓存，必须使用同一目录。
- 缓存没有自动清理期限。视频内容更新或需要重新识别/翻译时，可先停止工具，手动移走
  `outputs/.cache/` 作为备份，重启后会建立新缓存。当前不会自动恢复旧网页任务或未下载的 MP3。

翻译不完整时，网页提供补翻按钮，CLI 继续导出部分结果；方法说明会保留实际译文来源，
失败原因和恢复建议写入日志。

## 词典精翻排版（中文质量升级）

机器翻译是**逐条孤立**进行的，而字幕块常在句子中间切断（如 `...the moment you walked` / `out of the exam hall?` 分属两块），断句处必出误译；标题、习语也常直译。整段丢给词典翻译则语境完整，质量明显更好。推荐配合**仅拉英文模式**跳过机翻，不为占位中文浪费时间：

1. 生成时就跳过机翻：CLI 加 `--no-translate`；网页勾选「跳过机翻·仅拉英文」。
   产出的 md 只有英文行，头部标注「中文 `待词典对照`」。
2. 网页阅读页点「📋 复制英文全文」——得到**不换行英文整段**（空格拼接，对词典整段翻译友好），
   直接丢给词典（欧路词典会员支持长文整段翻译）。英文带硬换行会让欧路按行翻译、
   行间接缝出破碎译文（Unit 22 实测教训）；从这个按钮复制天然无此问题。
3. 词典输出的**整段中文**直接粘到阅读页右侧的「词典中文粘贴区」→ 点「🤖 一键排版」：
   后端无头调用本机 `claude` CLI，按每个字幕块的英文断句点切分对齐（句中被切断的块，中文跟着
   同一语义点切断，跨块连读仍是完整通顺的一句），段数校验后自动回填，头部来源说明改为
   「欧路词典对照」。全程不离开页面，约 1–2 分钟。
4. 兜底：一键排版失败（如 claude 不可用/段数不匹配重试无果）时，点「保存，交给 Claude 排版」，
   再到 Claude Code 对话里说「排版」——Claude 经 `GET /api/align/latest` 取材料、
   `POST /api/jobs/<id>/import-chinese` 回填，回页面点「⟳ 应用排版结果」。
5. 「下载 Markdown」即为最终双语稿（文件名 = 视频标题-双语字幕.md，直接放进对应书目文件夹即可）。
6. 上手机端：`cd tools/subtitle-viewer && python sync_subtitles.py`。

## 能处理什么

- B 站视频自带字幕和 B 站可访问的 AI 字幕。
- 无字幕轨的英文口播视频：网页和命令行都会下载临时音频，用 `faster-whisper small.en` 识别英文时间轴（只支持英文语音），再机器翻译中文。
- SRT、WebVTT，以及 B 站 `body/from/to/content` JSON 字幕结构。
- 两条中英文轨分段不一致：按时间重叠对齐；同一翻译覆盖多句英文时自动合并，减少重复。
- 单条双语轨：支持常见的“英文换行中文”“英文 | 中文”结构。
- 多 P 视频：链接带 `?p=N` 时读取指定 P；不带时取第 1 P。

## 当前边界

- 网页模式不下载视频；语音识别只临时下载音频（自动选最低码率音轨，Whisper 内部会重采样，高码率无收益），识别完自动删除，不落盘。
- 语音识别依赖是可选的：未装 `requirements-whisper.txt` 时网页会提示安装命令，其余功能不受影响。
- 任务进度在内存中，刷新后需重新读取链接；已完成转写和成功译文保存在本地，按上面的步骤复用。
- 中文语音视频暂不支持自动转写（Whisper 模型用 `small.en`，仅英文）。
- 机器翻译用 Google Translate / MyMemory 后端链（缓存优先、失败切换），结果需要抽查；MyMemory 对习语（如 over the moon）可能直译。
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
| `translation_store.py` | SQLite 转写/译文缓存，以及跨进程请求节流、冷却 |
| `translation_backends.py` | Google / MyMemory HTTP 适配、超时、额度/限流判定、UTF-8 分片 |
| `tts_bridge.py` | 引用 text2mp3 的 tts_core：行→朗读文本、分片合成、拼接 MP3 |
| `templates/index.html` / `static/*` | 电脑端双语阅读界面与语音识别进度 |

离线单测在根目录 `tests/test_bilibili_subtitles.py`；测试不访问 B 站。
