# 公网门户(portal)

47 站点的统一入口卡片页:http://47.108.230.162/
纯静态单文件(index.html,零 JS),手机优先 2 列 / 桌面 3 列卡片,点卡直达各功能。

## 收录的功能

| 卡片 | 地址 | 工具 |
|---|---|---|
| 🎧 我的书库 | `/script/` | audio-player |
| 📖 字幕跟读 | `/script/subtitles/` | subtitle-viewer |
| 🔤 单词复习 | `/script/vocab/` | vocab-review |
| 🎤 口语跟读 | `/script/speaking/` | speaking-player |
| 💬 口语话题 | `/script/topics/` | ielts-topics |
| 🧪 单词复习 β | `/script/vocab-beta/` | vocab-review(beta) |

## 新增功能卡片

编辑 `index.html` 的 `.grid`,复制一张 `<a class="card">>` 块改地址/文案即可。

## 部署

```bash
python upload.py    # 推为 /www/wwwroot/47.108.230.162/index.html
```

改版后若浏览器缓存旧页,强制刷新(Ctrl+F5)即可。
