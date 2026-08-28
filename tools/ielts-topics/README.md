# 走遍美国口语话题（ielts-topics）

按《新世纪走遍美国》（Connect with English）单元组织的 IELTS 口语练习页：
每单元 3–5 个话题（6–7 分难度、1–3 分钟、不分 Part），贴近单元剧情主题。
话题页 = 题目（中英）→ 思路提示（中文思路 + 英文表达）→ 单元词汇 →
参考范文（默认折叠，逐句/整段中英对照可切换）。
桌面端左侧「单元→话题」树 + 右侧内容区，手机端层级导航。纯静态。

## 数据来源与生成

- 源文件：`../../scripts/新世纪走遍美国-中英文台词.xls`（「合集」sheet，45 单元；U09 段内以 N010–N012 标记并入第 10–12 集内容，故无独立 U10–U12）
- `python scripts/extract_units.py` → `scripts/out/units.json`（台词中间产物，不提交）
- 话题数据：`data/topics.json`（Claude 逐单元分析生成，全 45 单元 188 话题）

## 本地预览

```bash
cd tools/ielts-topics && python dev_server.py          # http://127.0.0.1:8500
python dev_server.py --lan                              # 手机同 Wi-Fi 访问
```

## 部署与同步

见 sync_topics.py（前端 + topics.json 一键上服务器）与 nginx.conf.example（一次性 location 配置）。
线上：http://47.108.230.162/script/topics/
音频播放器书库页（本机/线上）会显示跳转卡片（audio-player/core.js 的 topicsHref 按环境指向本地 8500 或线上路径）。

## 测试

```bash
node --test                        # core.js 纯逻辑
pytest ../../tests/test_ielts_topics.py
```
