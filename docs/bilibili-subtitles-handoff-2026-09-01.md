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
- **2026-09-01 下午已跑通并生成产物**（`outputs/BV1C1t86wEM3/` 下 138 条 MD + XLSX，QA 通过）

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
5. 用 `deep-translator` 补齐中文（或缺失的英文）：**Google Translate → MyMemory 后端链自动切换**。
6. 写出 `.md` / `.xlsx`，临时目录退出时自动删除音频。
7. Markdown 会注明 Whisper/机器翻译方法，不冒充作者原生字幕。

### 4. 机器翻译后端链（2026-09-01 补充，TDD）

本机网络无法直连 Google（`translate.googleapis.com` 黑洞超时），单用 GoogleTranslator 必失败。
`direct_generate.py` 现在实现：

- 启动前 3 秒 HEAD 探测 Google，不可达直接不进链（deep-translator 请求无超时，黑洞连接会挂 20-40 秒/次）。
- MyMemory 兜底（免 key）：语言用全名（`english` / `chinese simplified`）；
  单条 500 字符上限，超长按句子边界自动分片（`split_for_limit`），译文按目标语言拼接（`join_parts`）。
- MyMemory 额度用尽时返回 HTTP 200 + "MYMEMORY WARNING: ..." 伪装成译文——已显式识别为后端失败。
- 运行中某后端重试耗尽会永久切换下一个；产物方法标注如实反映实际后端（如 `中文：MyMemory 机器翻译`）。
- 可选：环境变量 `MYMEMORY_EMAIL` 提额（匿名日额度有限）；有代理时设 `HTTPS_PROXY` 走回 Google。

可选依赖文件：`requirements-whisper.txt`。

## 本机/依赖状态

- Python：`3.12.10`
- Flask：已安装（`3.1.3`）
- yt-dlp：已安装（`2026.8.19`）
- `faster-whisper`：已安装（`1.2.1`，含 ctranslate2/PyAV，无需系统 ffmpeg）
- `deep-translator`：已安装（`1.11.4`）
- Whisper `small.en` 模型已缓存（首次运行已下载）
- 本机网络：无法直连 Google（翻译走 MyMemory 兜底）

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
- 翻译后端链（切换/分片/拼接/额度告警）、Google 探测、方法标签拆分

本轮记录：

- 2026-09-01 上午提交前全仓：`58 passed`
- 2026-09-01 下午（后端链 + 标签拆分）后全仓：`69 passed in 1.50s`

## 已完成的首个真实产物（2026-09-01）

```text
tools/bilibili-subtitles/outputs/BV1C1t86wEM3/
  Vocabulary in Use Advanced｜Unit 14 …-双语字幕.md   (138 条)
  Vocabulary in Use Advanced｜Unit 14 …-双语字幕.xlsx (141 行含表头)
```

QA 结论：

- Whisper `small.en`：专业词（antipathy / aversion / anti- 前缀族）识别准确；无幻觉循环；时间戳单调递增；块长 3–12s 适合阅读。
- 翻译：138/138 全部有中文，无漏译、无 "MYMEMORY WARNING" 泄漏；MyMemory 对习语会直译（over the moon → 飞越月球、table → 桌子），学习对照可用。
- 管道耗时：音频下载 ~10s + Whisper ~3.5min + MyMemory 翻译 ~4min。

## 下一步（可选）

- 若后续视频需要更好译文质量：设 `HTTPS_PROXY`（代理）走回 Google，或设 `MYMEMORY_EMAIL` 提高 MyMemory 日额度。
- 网页模式和一键模式仍是两个入口；网页遇到“无字幕轨”不会自动启动 Whisper。
- Excel 没有单独的“生成方法”元数据行；Markdown 有生成说明。
- B 站未登录时“没有字幕轨”和“登录后才展示字幕”有时难以区分；若用户明确允许，可尝试 `--browser edge`（或 chrome/firefox）。
- 机器翻译用于学习对照，不能视为出版级翻译。

## Git 范围提醒

提交时只包含本模块和相关文档/测试。仓库已有未跟踪目录：

- `.claude/`
- `audioplayer/`

它们不是本轮改动，**不要 stage、不要删除**。
