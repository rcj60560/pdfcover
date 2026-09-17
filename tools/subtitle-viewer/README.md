# 字幕跟读器（subtitle-viewer）

外部播放视频/音频（手机 B站App、电脑任意播放器）时，手机浏览器打开本页，
列表为两级：书目网格 → 书内 Unit 网格（?book=）。选对应字幕 MD，点「▶ 视频开始时点这里」开始对时——页面按时间插值连续滚动（换句不跳变），当前句保持居中。
不检测外部播放器进度；±1s/±5s 按钮校准，点任意时间戳重新锚定（视频拖动后用），⏸ 与视频同停；
时钟准则滚动准，滚动不会相对字幕独立漂移。
文档底部纯文本对照区（英文、中文各一大段，两张卡片各自带「📋 复制」）；顶栏「⬇ 纯文本」直达。
复制在 http 公网（非安全上下文）自动降级为 textarea + execCommand。

## 本地预览
cd subtitle-viewer && python dev_server.py    # http://127.0.0.1:8800（docs 读 config.json 的 src_root，无则 fixtures）
手机同 Wi-Fi 预览：python dev_server.py --lan

## 部署与同步
python sync_subtitles.py [--src 目录] [--dry-run]
线上：http://47.108.230.162/script/subtitles/
源目录默认 config.json 的 src_root；只上传含时间戳的 md（bilibili-subtitles 生成格式）。

## 字幕 md 格式
块间 `---` 分隔；每块：`00:00:08 → 00:00:14`（反引号）+ `**英文**` + 中文段落。
无时间戳的 md 降级为静态阅读模式。

## 剑桥雅思词汇管线（cambridge/）
《剑桥雅思核心词汇精讲精练》书后 Recording scripts → 时间轴双语字幕：
OCR 提取 → faster-whisper 词级转写 → difflib 词序对齐 → 人工/LLM 翻译 → 生成 md。

```bash
cd tools/subtitle-viewer
python -m cambridge.run --dry          # 只出映射/置信报告
python -m cambridge.run --only 1a      # 只生成一条
python -m cambridge.run                # 全量（48 条 → src_root/剑桥雅思核心词汇精讲精练/）
```

- 源数据：全本 `_OCR.pdf` + 49 条 Track 音频（路径见 run.py 常量）；中间产物缓存于仓库 `tmp/cambridge_cache/`（recordings.json / Track*.words.json / match.json），可重跑。改 extract.py 后需删 `tmp/cambridge_cache/recordings.json` 再跑，否则仍读旧提取缓存。
- 翻译：`cambridge/translations/{id}.json`，键 = turn 序号（字符串）；1a–2b 为用户精翻稿，其余为 LLM 翻译待抽查。
- 已知数据妥协：22b 说话人 "I" 被 OCR 成 "1" 并入 H 段；词表类录音为单块长段。
- 数据修复记录：15a “Statement 1/2/3” 题号曾被尾部裸页码剥除，已收窄规则（尾部裸页码仅当前邻为句末标点/逗号时剥除）；OCR 噪声用定点覆盖表 `TEXT_OVERRIDES`（count 守卫）清理：15b/22a/6a 尾部页脚乱码串删除、16 的 CO»→CO₂。
- 音频在音频站（/script/books/剑桥雅思核心词汇精讲精练/）播放，字幕页手动对时跟读。

## 测试
node --test                       # core.js 纯逻辑
pytest tests/test_subtitle_viewer.py
pytest tests/test_cambridge_pipeline.py   # 剑桥管线纯逻辑
