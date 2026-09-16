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

## 测试
node --test                       # core.js 纯逻辑
pytest tests/test_subtitle_viewer.py
