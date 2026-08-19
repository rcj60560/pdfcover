# 口语跟读播放器（speaking-player）

卡拉OK 式口语跟读页：MP3 + 同名 timeline json（词级时间轴，由 text2mp3 生成）→
大字幕当前句居中、逐词高亮、点词跳转、单句循环、逐句模式（句尾停 N 秒自动下一句，1/2/3/5s 可调）、
倍速、中文翻译。纯静态，手机优先。

## 本地预览
cd speaking-player && python dev_server.py    # http://127.0.0.1:8400
真实音频放 fixtures/tracks/（X.mp3 + X.json，gitignore；用 tools/text2mp3/tts_cli.py 生成）

## 测试
node --test                       # core.js 纯逻辑
pytest tests/test_speaking_player.py

## 部署与同步
见 sync_speaking.py（音频+前端一键上服务器）与 nginx.conf.example（一次性配置）。
线上：http://47.108.230.162/script/speaking/

## timeline json 格式
{ "voice","rate","pitch","translation",
  "words":[{"t","s","d"}](ms), "sentences":[{"text","i","j","start","end"}](ms) }
无 json 的 mp3 自动降级为无字幕播放。
