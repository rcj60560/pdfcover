# 字幕跟读器（subtitle-viewer）设计

- 日期：2026-09-11
- 状态：设计已评审通过（brainstorming 全流程），待实施
- 关联：`tools/bilibili-subtitles`（字幕 MD 生成端）、`tools/speaking-player`（部署模式参照）

## 背景与目标

B站字幕工具已能产出「时间戳 + 英文 + 中文」的字幕 MD。目标：视频/音频在**外部**播放（手机 B站App 后台、电脑任意播放器）时，手机浏览器打开网页，选中对应字幕 MD，页面**按播放进度自动滚动**跟读。

对时方式（已定）：**手动对时**——不检测外部播放器进度（也检测不到），页面自己按墙上时钟推算；精度要求几秒内，配 ±5s 按钮校准。

**非目标（本期不做）**：检测 B站App/网页播放进度、本地音频精确同步播放器、字幕编辑、SRT/VTT 导入、访问鉴权、增量同步优化。

## 总体架构（数据流）

```
字幕 MD（Ahuaxi 本地目录，bilibili-subtitles 生成）
  ─(sync_subtitles.py)→ 服务器 /script/subtitles/docs/ + 静态 manifest.json
手机浏览器 → http://47.108.230.162/script/subtitles/
  → 列表（fetch manifest.json）→ 点一篇 → fetch MD → core.js 解析
  → 点「开始」对时 → 按时钟自动滚动 + 高亮当前句
本地预览：python dev_server.py（/docs/** 映射本地目录，/manifest.json 动态生成）
```

纯静态无后端；nginx 走已有 `/script/` 静态托管，无需新配置。

## 字幕 MD 格式（输入契约）

`tools/bilibili-subtitles` 生成的格式，块间 `---` 分隔：

```markdown
`00:00:00 → 00:00:06`

**Today we're diving into unit 1 ...**

今天我们将深入学习第一单元 ...

---

`00:00:08 → 00:00:14`

**Quick question, ...**

弱弱的问一句，...
```

- 时间戳行：`` `MM:SS → MM:MM` `` 或 `` `HH:MM:SS → HH:MM:SS` ``（倒计时格式不出现）
- 头部 `<style>`、blockquote 元信息、一级标题：解析时跳过
- 无时间戳的普通 md → 降级「静态阅读模式」（可浏览，不计时滚动）

## 前端（tools/subtitle-viewer，纯静态零依赖）

文件：`index.html` / `app.js` / `core.js` / `style.css`，单页两视图：

- **列表视图**：manifest 按目录分组展示，显示标题 + 条数/时长
- **字幕视图**：整篇渲染，英文大字、中文小字；当前块高亮 + 平滑滚到屏幕中部

交互：

- 进入字幕视图后**待命**，中央大按钮「▶ 视频开始时点这里」，点下才开始计时
- `−5s` / `+5s` 调 `offsetMs`；点任意块时间戳 → 以该块 start 重新锚定（视频拖动后用）
- ⏸/▶ 暂停继续（两侧时钟一起停）；播完最后一块 → 停住提示「已结束」
- 手动上滑 → 暂停自动跟随，浮出「↓ 回到当前」按钮
- 手机常亮 `navigator.wakeLock`（失败静默降级）
- 手机优先 UI；URL 带 `?doc=` 直达某篇

## 核心逻辑（core.js，纯函数，node --test）

- `parseSubtitleMd(text) -> { blocks: [{startMs, endMs, en, zh}], hasTimestamps }`
- `Clock` 对时：`elapsed = now − t0 + offsetMs − 累计暂停`；±5s 改 offsetMs；锚定 = 让 elapsed 立即等于所点块的 startMs（等价于重置 t0）
- `currentBlock(blocks, elapsedMs)`：`start ≤ t < end` 命中；间隙保持上一块；超过最后一块 → 结束态

## 同步与部署（sync_subtitles.py）

- 配置 `config.json`：`{ "src_root": "D:\\Users\\luocj\\Ahuaxi\\hcrs_devdocs\\ielts" }`（`--src` 可覆盖）
- 递归收集含时间戳的 .md（Python 侧轻量正则验证「含至少一个时间戳行」，完整解析在前端 core.js）
- scp 上传：前端 4 文件 → `/script/subtitles/`；MD → `/script/subtitles/docs/`（保留相对路径）；生成 manifest.json（标题、相对路径、条数、总时长）并上传
- `--dry-run` 只打印；上传后 `chown -R www:www`（同 speaking-player）

## 本地预览（dev_server.py）

- 托管前端静态文件；`/docs/**` 映射 `src_root`；`/manifest.json` 动态扫描生成（与线上格式一致）→ 本地线上同一份前端
- `--lan` 打印局域网地址（同 speaking-player）
- 注册 kit 面板：`tool.toml`，端口 8800

## 测试

- `node --test`（core.test.js）：MD 解析（标准/头部跳过/无时间戳降级/两种时间戳格式/多块）、currentBlock（命中/间隙/结束）、Clock（±5s、锚定、暂停恢复）
- `pytest tests/test_subtitle_viewer.py`：sync 的 MD 收集与筛选、manifest 生成、dev_server 的 manifest/路径映射

## 错误处理

- manifest 为空 → 列表页提示「先跑 sync_subtitles.py 上传字幕」
- fetch MD 失败 → 提示重试返回列表
- MD 无时间戳 → 静态阅读模式降级，按钮区隐藏
