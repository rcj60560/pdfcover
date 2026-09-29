# 单词复习(vocab-review)

字幕文章库 → 个人词池 → SM-2 间隔复习。手机优先的公网静态站,零后端依赖。
实现细节/组件/规则全记录见 [ARCHITECTURE.md](ARCHITECTURE.md)。

## 线上

- 主站:http://47.108.230.162/script/vocab/ (字幕站顶栏「🔤 单词复习」也有入口)
- Beta:http://47.108.230.162/script/vocab-beta/ (雅思词书增强版,英英/短语/有道例句)
- 两站进度独立(localStorage);浏览器建议 Chrome(手机/电脑均可)

## 使用(手机)

- 卡片直显:词+音标+🔊+释义+例句,点 😒不认识 / 😃认识 判定;连认 4 次或间隔≥21 天毕业
- 自动发音默认开(有道词典真人录音,⚙ 可切英音/美音,断网回退系统语音)
- 完成今日队列后可「➕ 继续复习」加一批;◀▶ 回看已判过的卡
- 顶部搜索框即搜全词池,点结果进详情页
- ⚙ 设置:每日新词上限 / 自动发音 / 发音偏好 / 导出·导入进度(**导入是覆盖**) / 📖 词库总览(字母分节+状态筛选+毕业进度) / 📊 统计报表(正确率+近7日趋势) / 🗑 重置
- 注意:进度按设备隔离;跨设备迁移用 导出→导入

## 构建(电脑,新增文章后跑一遍)

```bash
cd tools/vocab-review
python build.py                                  # 扫描字幕库 → web/vocab.json(需 tmp/ecdict/stardict.db)
python enrich.py                                 # 雅思词书增强 → web/vocab-beta.json(可选,需 tmp/kajweb/*.json)
python upload.py                                  # 主站部署
python upload.py --dir vocab-beta --vocab web/vocab-beta.json   # beta 部署
```

- 字幕库目录默认取 subtitle-viewer config.json 的 src_root;`--src/--ecdict/--out/--level` 可覆盖
- ECDICT sqlite 首次准备:GitHub ECDICT releases 下载 ecdict-sqlite-28.zip,解压出 stardict.db 放 tmp/ecdict/
- 雅思词书:kajweb/dict 仓库 book/ 下 IELTSluan_2.zip + IELTS_3.zip(github.com 被墙时走 api.github.com blobs API)
- 手机进度不随词池更新丢失(按词形原形为键)

## 本地预览

```bash
cd tools/vocab-review/web && python -m http.server 8890   # http://127.0.0.1:8890(file:// 打不开,有 CORS)
```

## 测试

```bash
python -m pytest tests/test_vocab_review.py -q   # 构建/增强纯逻辑
cd web && node --test                            # SM-2/队列/存储/分组纯逻辑
```
