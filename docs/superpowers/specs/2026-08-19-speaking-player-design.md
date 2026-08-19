# 口语跟读播放器（speaking-player）设计

- 日期：2026-08-19
- 状态：设计已评审通过（brainstorming 全流程），待实施
- 关联：`tools/text2mp3`（生成端）、`tools/audio-player`（部署模式参照）、IELTS 口语工作流（Obsidian 库）

## 背景与目标

IELTS 口语回答已能通过 text2mp3（edge-tts）一键生成 MP3。目标：让音频连同**词级时间轴字幕**一起上服务器（47.108.230.162），在任何设备（重点手机）打开网页即可**卡拉OK 式逐词高亮跟读**。

**非目标（本期不做）**：录音跟读对比、服务端 AI 对齐、访问鉴权（站点本就公网）、增量同步优化（目录小，全量幂等）、VTT/SRT 导出（以后可从 json 加导出器）。

## 总体架构（数据流）

```
素材.md 话题 ─(Claude)→ 口语回答笔记 + 英文 txt
            ─(tts_cli.py)→ 本地 音频/话题N-标题.mp3 + 话题N-标题.json
            ─(sync_speaking.py)→ 服务器 /script/speaking/tracks/
设备浏览器 → http://47.108.230.162/script/speaking/ → 纯静态播放页 → 卡拉OK 跟读
```

关键决策：**时间轴来自 TTS 引擎原生的 WordBoundary 事件**（每个词的起始+时长），生成时顺手落盘，零对齐成本、精确匹配音频。

## 数据格式（timeline JSON）

与 MP3 同名共存（`话题1-为什么我要学英语.mp3` + `.json`）：

```json
{
  "voice": "en-US-AvaMultilingualNeural",
  "rate": "+0%", "pitch": "+0Hz",
  "words": [{"t": "To", "s": 0, "d": 210}, {"t": "me,", "s": 240, "d": 180}],
  "sentences": [{"i": 0, "j": 9, "start": 0, "end": 12500}],
  "translation": "可选：整段中文翻译"
}
```

- `s`/`d`/`start`/`end` 单位**毫秒**（edge-tts 原生 100ns 单位 ÷ 10000）
- `sentences.i/.j` 为该句在 `words` 里的下标区间；由词表句末标点（`. ! ?`）推导，句内无词的空句丢弃
- `translation` 由 Claude 生成笔记时可选写入（网页端开关显示）

## 生成端改造（text2mp3，小改）

- `_synthesize` 改为流式收集：一边写 MP3 一边收 `WordBoundary(chunk.stream())` 事件
- 合成完成 → `resolve_output_path` 同目录写同名 json（words + sentences 推导）
- 网页端（`/api/tts`）与 CLI（`tts_cli.py`）两条路都出 json，逻辑收敛在 tts_core 新函数（如 `build_timeline(events) -> dict`，纯函数可单测）
- 旧 MP3（无 json）不受影响，播放器降级为无字幕播放

## 同步与部署（tools/speaking-player/sync_speaking.py）

- 源：默认 `D:\Users\luocj\Obsidian\IELTS\IELTS\学习记录\口语回答\音频`（读 text2mp3 的 config.json 可覆盖）
- 目标：`root@47.108.230.162:/www/wwwroot/47.108.230.162/script/speaking/`
  - `tracks/` ← 全量 scp 音频+json（幂等；文件名即曲目名）
  - 前端 4 文件（index.html/app.js/core.js/style.css）也一并上传
  - 上传后 `chown -R www:www`
- nginx：在宝塔 extension 目录 `/www/server/panel/vhost/nginx/extension/47.108.230.162/speaking.conf` 加 location（alias 到 speaking 目录 + `autoindex json`），照抄 audio-player 的 conf 模式，`nginx -t && nginx -s reload`
- 依赖服务器 ssh 可登录；未配免密则每次输密码（脚本不强制要求免密）

## 播放端（tools/speaking-player，纯静态零依赖）

- 文件结构对齐 audio-player：`index.html / app.js / style.css / core.js`；`core.js` 为纯逻辑（node --test 单测）；`dev_server.py` 本地预览（`/tracks/` 映射 `fixtures/tracks/`，返回同 nginx 格式的 autoindex json）
- 曲目列表：`GET tracks/` autoindex → mp3 列表；存在同名 `.json` 标记「字幕可用」
- 播放页：
  - 大字幕区：**当前句居中**展示，句内**逐词高亮**（已读词着色），随播放自动滚动
  - 点任意词 → seek 到该词起点
  - 中文翻译开关：字幕下方显示 `translation`
  - 控件：倍速（0.6 / 0.8 / 1.0 / 1.25）、**单句循环开关**（区间 = 当前句 start/end，句尾自动回句头）、上一句 / 下一句、单句重播
  - 手机竖屏适配（跟读主场景在手机）
- 高亮驱动：`requestAnimationFrame` 对照 `audio.currentTime`，`core.js` 提供当前词二分查找

## 错误处理与降级

- json 缺失或损坏 → 无字幕普通播放（不报错）
- autoindex 请求失败/解析失败 → 空列表 + 提示「曲目加载失败」
- 音频 404 → toast 提示
- seek/循环区间越界 → clamp 到音频时长

## 测试策略

- `core.js`（node --test）：句子切分（含省略号/多标点）、当前词二分查找边界、单句循环区间判断
- pytest（根 tests/）：`build_timeline` 用假 WordBoundary 事件断言结构；sync 脚本的纯逻辑（远端/本地文件清单对比）用临时目录测
- 手动验收（见下）

## 验收清单

1. `tts_cli.py` 生成话题1 → 音频目录同时出现 `.mp3` + `.json`，json 结构合法
2. 本地 `python dev_server.py`：列表出现曲目；逐词高亮跟手、点词跳转、单句循环、倍速、翻译开关全部正常
3. 跑 `sync_speaking.py` → 手机访问 `http://47.108.230.162/script/speaking/`，功能与本地一致
4. 旧的无 json MP3 放入 tracks/ → 可播放、无字幕、不报错
