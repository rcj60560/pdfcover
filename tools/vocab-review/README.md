# 单词复习（vocab-review）

字幕库里的划线英文词自动做成生词卡，手机网页间隔复习。`build.py` 从字幕 md 的
`**加粗英文行**` 收词，经 ECDICT 标签/词频分级——高考（gk）以下视为已会直接丢弃，
cet4/ky/toefl 等标签的生词候选连同原句例句生成 `web/vocab.json`；页面纯静态，
复习进度存在浏览器 localStorage，不依赖任何后端。

## 使用（构建 → 上传）

首次准备 ECDICT：从 [skywind3000/ecdict](https://github.com/skywind3000/ecdict) releases
下载 `ecdict-sqlite-28.zip`，解压出 `stardict.db` 放到仓库根 `tmp/ecdict/stardict.db`
（或用 `--ecdict` 另指路径）。

```bash
cd tools/vocab-review
python build.py     # 字幕 md → web/vocab.json（源目录读 subtitle-viewer config.json 的 src_root）
python upload.py    # scp web/ 五件套 → 服务器 /script/vocab/
```

`upload.py --build` 可一步到位：先重新构建再上传。**新增文章后**照此重跑一遍——
字幕库同步（subtitle-viewer `sync_subtitles.py`）→ `python upload.py --build`，
词池与例句即包含新内容。

线上地址：http://47.108.230.162/script/vocab/ （字幕站顶栏「🔤 单词复习」直达）。

## 进度与备份

- 复习进度（每词的间隔天数、到期日、连续认识次数）只存本机浏览器的
  localStorage（key `vocab-review-state-v1`），不上服务器。
- 换设备 / 清缓存前：⚙ 设置 →「导出进度」存一份 json；新设备「导入进度」恢复。
  导入文件会先校验格式，不对则拒绝且不影响当前进度。
- 隐私模式存不进 localStorage 时，页面顶部有横幅提醒（进度只在本页有效）。

## 本地预览

```bash
cd tools/vocab-review/web
python -m http.server 8890    # 打开 http://127.0.0.1:8890
```

直接双击 index.html（file://）不行——fetch vocab.json 会被浏览器拦。

## 结构

| 文件 | 职责 |
|---|---|
| `build.py` | 字幕 md → 划线词分级筛选 → `web/vocab.json` |
| `ecdict.py` | ECDICT sqlite 只读查询、词形还原（stardict.db） |
| `upload.py` | scp `web/` 五件套到服务器 `/script/vocab/`，结尾 chown |
| `web/index.html` · `app.js` · `style.css` | 复习页：卡片流（翻面自测 + 认识/不认识）与设置抽屉 |
| `web/core.js` | 队列、SM-2 简化调度、进度导入导出（纯逻辑） |

离线单测在根目录 `tests/test_vocab_review.py`（pytest）；前端纯逻辑测试
`web/core.test.js`（`cd web && node --test`）。测试不访问网络、不上传。
