# 交接文档:字幕站两级导航 + 剑桥雅思词汇字幕管线

> 写于 2026-09-17。**状态:两个计划均已全部完成并上线(2026-09-17 收官)**——本文档转为历史记录,「下一步」章节仅作流程回顾。当前线上:http://47.108.230.162/script/subtitles/ 共 68 篇(剑桥书 48 篇,两级导航 v=8)。管线重跑/维护入口见 `tools/subtitle-viewer/README.md` 剑桥管线一节;已知妥协与修复记录同处。

## 一、用户要什么(最终意图)

用户的学习工具箱 `D:/Users/luocj/pyProject/ky/tools` 里有一个**字幕跟读器**(tools/subtitle-viewer,线上 http://47.108.230.162/script/subtitles/ ):手机上外部播放视频/音频(B站App、音频站),浏览器打开字幕页,手动对时后页面按时间插值连续滚动、当前句居中高亮。字幕 md 格式:块间 `---`,每块 `` `M:SS → M:SS` `` 时间戳 + `**英文**` + 中文行。

本阶段两大需求:

**A. 两级导航(✅ 已完成)**:原来一级列表平铺 20 篇字幕,改为「书目网格 → 书内 Unit 网格」两级,卡片完整显示名称,手机 2 列/宽屏 3 列。

**B. 剑桥雅思词汇 → 时间轴字幕(🔶 进行中,本交接重点)**:把《剑桥雅思核心词汇精讲精讲》(Pauline Cullen)书后 Recording scripts(43 条,1a–22b,16/18/21 单元无录音)做成双语时间轴字幕 md。**用户已拍板的关键决策**:

1. **音频同步用跨页手动对时**(现状机制):音频在音频站(http://47.108.230.162/script/ )播,字幕页点「▶」对时、±1s/±5s 追——subtitle-viewer 播放行为**零改动**,明确不做同页内嵌音频。
2. **翻译分工**:1a–2b 用用户已有的精翻稿;**3a 起由 agent 全部先翻**(带上下文逐段,保留说话人标签),用户抽查,个别不满意再走词典流程替换。
3. 输出 md 目录:`D:/Users/luocj/Ahuaxi/hcrs_devdocs/ielts/剑桥雅思核心词汇精讲精练/`(src_root 下的新书目,上线后自动出现在书目网格)。

## 二、权威文档在哪(按优先级)

| 文档 | 路径 | 说明 |
|---|---|---|
| **Spec(权威)** | `docs/superpowers/specs/2026-09-16-subtitles-two-level-nav-and-cambridge-vocab-pipeline-design.md` | 需求与决策的最终依据,冲突以它为准 |
| **Plan(实施方案)** | `docs/superpowers/plans/2026-09-16-cambridge-vocab-pipeline.md` | T1–T7 任务书,含全部实现代码、测试、验收命令。**T1 已完成,T2 起照做** |
| SDD 台账 | `.superpowers/sdd/2026-09-16-cambridge-vocab-pipeline/progress.md` | 每任务状态、修复轮记录、裁定清单(续接必读) |
| 各任务简报 | 同目录 `task-N-brief.md`(N=2..7 已生成) | 单任务自包含需求,派子代理时直接引用 |
| 姊妹计划 | `docs/superpowers/plans/2026-09-16-subtitles-two-level-nav.md` | 已完成的两级导航,仅供了解 |

## 三、源数据与既有资产

| 资产 | 路径 | 状态 |
|---|---|---|
| OCR 全本 PDF(提取源) | `D:/夸克下载/剑桥雅思核心词汇精讲精练/剑桥雅思核心词汇精讲精练_OCR.pdf` | 180 页文本层,脚本区 163–172 页,43 条录音。**用这份,不是 OCR_p163-180.pdf** |
| 扫描原 PDF | 同目录 `(Pdg2Pic, ...).pdf` | 无文本层,备用 |
| 音频 49 条 | `D:/夸克下载/剑桥雅思核心词汇精讲精练/剑桥雅思核心词汇精讲精练  音频/Track01.mp3..Track49` | 音频站已上线 |
| 用户精翻稿(1a–2b) | `D:/夸克下载/剑桥雅思核心词汇精讲精练/录音脚本_Recording1a-2b_中英对照.md` | 高质量,Task 6 转成 translations JSON 用 |
| 已交付代码 | `tools/subtitle-viewer/cambridge/{__init__.py, extract.py}` | T1 产物 |
| 已交付测试 | `tests/test_cambridge_pipeline.py` | 3 个测试 |
| 中间产物缓存 | `tmp/cambridge_cache/`(repo 根) | T5 起写入(recordings.json、Track*.words.json、match.json) |
| Whisper | faster-whisper small.en 已随 bilibili-subtitles 装好 | `python -c "import faster_whisper"` 可验证 |

## 四、下一步做什么(按 Plan 顺序)

**T2 词级对齐 `cambridge/align.py`**(plan Task 2,brief 已生成):TDD 实现 `normalize_word/words_of/align_turns/match_tracks`。核心:difflib SequenceMatcher 对「脚本词序列 × whisper 词序列」,equal 块映射时间;无匹配 turn 邻居插值 conf=0;录音↔Track 用开头词相似度 ≥0.5 最佳配对。

**T3 Whisper 转写 `cambridge/transcribe.py`**(plan Task 3):faster-whisper word_timestamps=True,逐 Track 词级 JSON 缓存。无单测,I/O 模块,首个 Track 冒烟即可。

**T4 md 生成器 `cambridge/build_md.py`**(plan Task 4):TDD,`fmt_ts/build_md`,块=Speaker 一段,块结束=下一块起点。

**T5 编排 `cambridge/run.py` + `units.json`**(plan Task 5):全流程 + `--dry` 映射报告 + `--only 1a`。注意 run.py 里翻译 JSON 键 str→int 转换已写进 plan(修过的一个 bug)。units.json 25 个 Unit 标题从书目录/公开 TOC 填,Unit 1=Family、2=Childhood & Memory(以精翻稿为准)。

**T6 精翻转换 + 1a 端到端**(plan Task 6):把精翻稿 1a–2b 手工转成 `cambridge/translations/{1a..2b}.json`(键=turn 序号,与 recordings.json 的 turns 顺序对齐);跑 `python -m cambridge.run --only 1a` 产 md;**用户试听验收后再批量**(时间轴 ±2s 内可接受)。

**T7 全量翻译 + 上线**(plan Task 7):agent 逐条翻 3a–22b(内容任务,分批 commit);批量生成;`python sync_subtitles.py` 上线;公网书目网格应出现「剑桥雅思核心词汇精讲精练」卡片。

**执行方式**:用户选了子代理驱动(superpowers:subagent-driven-development)。台账在 `.superpowers/sdd/2026-09-16-cambridge-vocab-pipeline/progress.md`,T1 已标 complete,**从 T2 起派发**。计划里代码齐全的任务用 haiku 转录+测试即可;内容翻译任务(T6/T7)需要中英互译能力,用更强模型。每个任务:实现 → review-package → 审查 → (修复循环) → 台账落行。

## 五、重要裁定(已定,不要重新发明)

1. 在 main 分支直接开发(用户自己 push,从不用分支)。
2. 跨页手动对时,不做同页音频。
3. 3a 起翻译 agent 全翻,用户抽查。
4. OCR 源用全本 `_OCR.pdf`。
5. diff 标准库(difflib),不引入 rapidfuzz。
6. 提交信息前缀 `feat(cambridge):` / `fix(cambridge):`,结尾 `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`。
7. 含中文输出的 python 命令加 `PYTHONIOENCODING=utf-8`(Windows GBK 控制台)。

## 六、已知问题与递延项(不阻塞 T2+)

- **22b 说话人 "I" 被 OCR 成 "1"**,保守规则并入 H 段的 text(数据级妥协,可接受;想修就在生成后人工把 H 段拆回两段)。
- no-colon 保守门有理论误切窗口(≥2 行首单字母 rubric 行在冒号标签前 → 整条录音静默丢失)。**本书数据不触发**(复审对抗探针验证);若未来换书复用管线需加固。
- 台账 minor 递延:导航计划的「其他」哨兵双份编码、?doc 返回落书目网格(spec 明文不动)、死 CSS `.group/.docs`、README `?book=` 反引号——都不阻塞。
- 公网 manifest 缓存问题已根治(fetch no-store, v=7);前端三处缓存版本号规则:v=8 现行,改 JS/CSS 必须三处同步升版(index.html 两处 + app.js 内 core.js import)。

## 七、验证与上线速查

```bash
cd tools/subtitle-viewer && node --test          # 前端纯逻辑(13 个)
python -m pytest tests/ -q                        # 含 test_cambridge_pipeline.py(3 个)
cd tools/subtitle-viewer && python dev_server.py # 本地 http://127.0.0.1:8800
python sync_subtitles.py                          # 上线公网(ssh/scp,末行「完成」即成功)
```

## 八、相关提交(本阶段,均在本地 main)

`02662f2` groupBooks → `5f010dd` v7 no-store 补提交 → `db4ef77` 两级路由网格 → `4426f44` README → `f8cf5b7` 死 import 清理 → `545fb78` cambridge extract → `e141d96` 22b 修复。更早:6705651(连续滚动)、ecc793a(自然序)、25daf52(词典精翻工作流文档)等。
