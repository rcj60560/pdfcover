# 文本转语音 MP3（text2mp3）

粘贴文本 → 微软神经语音（[edge-tts](https://github.com/rany2/edge-tts)）朗读 → 导出 MP3。
本来为 IELTS 口语回答跟读做的：把 Claude 生成的 7 分回答转成音频，放进 Obsidian 笔记库听。

## 使用

```bash
pip install -r requirements.txt     # edge-tts + flask
python app.py                       # http://127.0.0.1:8300 （或面板点启动）
```

页面：左侧贴文本，右侧设置（语音/语速/音调/文件名/输出目录）。

1. 粘贴文本（中英文均可）
2. 语音：**新一代 Ava / Emma / Andrew / Brian 韵律最自然**（推荐组）；另有经典英/美音、中文
3. 音调发「怪」时微调 pitch（-5 ~ -10Hz 常常更顺耳）；跟读建议语速 -10% ~ -20%
4. 输出文件夹默认 `D:\Users\luocj\Obsidian\IELTS\IELTS\学习记录\口语回答\音频`，可改，**上次选择会被记住**（`config.json`，已 gitignore）
5. 生成后页面内直接试听、跳转资源管理器定位文件

## 命令行（自动化用）

```bash
python tts_cli.py 回答.txt -n 话题1-为什么我要学英语 [-v 语音ID] [-r -10] [--pitch -5] [-o 输出目录]
```

UTF-8 文本文件 → MP3，成功打印路径；不写 config.json（不动网页端记忆）。
配合 Claude 会话用：生成口语回答笔记后直接落音频 + 在笔记里嵌 `![[xxx.mp3]]`。

## 结构

| 文件 | 职责 |
|---|---|
| `app.py` | Flask 入口（页面 + `/api/tts` 合成 + `/api/play` 试听 + `/api/reveal` 定位文件） |
| `tts_cli.py` | 命令行入口（自动化/脚本调用） |
| `tts_core.py` | 纯逻辑：语音表、文件名清洗、语速/音调格式、配置读写（单测在这层） |
| `templates/index.html` | 单页面板（左内容右设置） |

测试：根目录 `tests/test_text2mp3.py`（`pytest` 随全仓一起跑）。

## 说明

- 合成走 edge-tts 公共接口，需联网；失败时页面会显示原始错误
- `/api/play` 只允许播放在当前配置输出目录内的 `.mp3`，避免任意文件读取
- 语音清单位于 `tts_core.py` 的 `VOICES`，要加声音改那里即可
