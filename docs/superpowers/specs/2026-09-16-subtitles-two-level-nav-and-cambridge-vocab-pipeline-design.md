# 字幕站两级导航 + 剑桥雅思词汇字幕管线 设计

日期:2026-09-16
状态:已确认(对话中逐项拍板)

## 背景

- `/script/subtitles/` 一级列表平铺 20 篇字幕,随书目增多不可持续。
- 新学习内容:剑桥雅思核心词汇精讲精练(扫描 PDF,书后 Recording scripts 自印 157 页起;49 个 Track 音频已在音频站上线)。要做成与 B 站跟读完全同构的字幕:音频站播 Track、字幕页手动对时、连续滚动高亮。

## 已拍板的决策

| 决策点 | 结论 |
|---|---|
| 音频同步方式 | **跨页手动对时**(现状机制,subtitle-viewer 播放行为零改动) |
| 3a 起的翻译 | **Claude 全部先翻**,用户抽查;个别不满意走词典流程替换 |
| 1a–2b 翻译 | 直接用用户已有精翻稿 `录音脚本_Recording1a-2b_中英对照.md` |
| 导航形态 | 两级:书目网格 → 书内 Unit 网格,对齐线上音频站书库观感 |

## 需求 A:两级导航(前端)

- 路由:无参数 → 书目网格;`?book=<dir>` → 该书网格;`?doc=` 不变。
- 数据:manifest 结构不变。前端新增纯函数 `groupBooks(docs) -> [{dir, count, durationSec}]`(根目录散文档归「其他」);`groupManifest()` 保留给书内页。
- 样式:手机 2 列 / 宽屏 3-4 列等高卡片,标题两行内完整显示;卡片含标题 + N 条 + 时长。
- 交互:书内页顶栏「‹ 列表」→ 返回书目网格。
- 缓存版本升 v=8。

## 需求 B:内容管线

产物:每条 Recording 一个 md,置于 `src_root/cambridge-vocab/`,文件名 `Recording 1a｜Unit 1 Family.md`(自然序天然正确)。块 = Speaker 一段,格式与现有字幕 md 完全一致(`---` 分块 + `` `start → end` `` + `**English**` + 中文)。

管线五步(新脚本 `tools/subtitle-viewer/build_cambridge_vocab.py`,Whisper 能力复用 bilibili-subtitles 的 faster-whisper 安装):

1. **补 OCR**:现有 `OCR_p163-180.pdf` 覆盖到 Recording 22b 附近;其后页面用 pdf-ocr 工具补跑,缺页列清单。
2. **提取清洗**:OCR PDF → 中间 JSON `{recording, unit, title, speakers:[{label, text}]}`;自动修 `|→I`、`abie→able` 类错;对话体保留 `Speaker:` 标签。
3. **Whisper 对齐**:逐 Track 转写(faster-whisper small.en)→ 文本规范化(大小写/标点/撇号)→ 与脚本逐句模糊匹配(rapidfuzz 或 difflib)→ 每 Speaker 段 start/end。Track↔Recording 映射自动校验:转写首句 vs 脚本首句相似度阈值,对不上报警跳过。对不齐的句段在 Track 内按比例摊时间并记日志。
4. **翻译**:1a–2b 转换精翻稿格式;3a 起由 Claude 逐段翻(保留 Speaker 标签),写入翻译 JSON(与生成解耦,可单独重翻)。
5. **生成 md + sync**:批量产出 → `python sync_subtitles.py`,新书目自动出现在两级导航。

## 容错与边界

- 无人声/前奏 Track:跳过并列清单。
- OCR 识别错清洗后仍存疑:生成时标注,人工抽查清单输出。
- 对齐置信度低的 Recording:整条退化为「Track 起止均匀摊」并标注,不阻塞其他。
- 管线可重跑:中间 JSON 落盘,Whisper/翻译结果缓存(复用 bilibili 的 translation_store 思路或简单 json 缓存)。

## 测试

- `groupBooks()` 进 core.test.js(node)。
- 管线对齐函数(纯逻辑:规范化、模糊匹配、时间摊分)用 fixture 单测放 `tests/`。
- 端到端:先只跑 Recording 1a 验收(时间轴准、翻译对位、viewer 正常滚动),再批量。

## 不做的事(YAGNI)

- 不在字幕页内嵌音频播放(已选跨页手动对时)。
- 不改 manifest 结构、不改 sync_subtitles。
- 不做 OCR 缺页的自动重扫,只列清单人工补。
