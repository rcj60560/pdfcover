# 词汇复习工具(vocab-review)设计

日期:2026-09-28 · 状态:已与用户对齐(方案/算法/UI 均确认)

## 1. 背景与目标

用户公网字幕库(60 篇双语字幕,持续新增)是一座个人词汇池。目标:把这池子变成
Anki 式复习工具——按用户当前水平(雅思约 4 分)圈出"大概率不认识"的词,逐卡复习,
认识 → 间隔递增直至毕业,不认识 → 重置重现,最终把池内词汇记牢。

**核心决策记录**(与用户逐条确认):

| 决策点 | 结论 |
|---|---|
| 使用场景 | 公网手机为主;电脑同页可用(响应式单列) |
| 进度存储 | 手机端 localStorage + 导出/导入 JSON 备份;无后端 |
| 生词判定 | ECDICT 词级标签划线:中考/高考 = 默认已会;CET4/CET6/考研/雅思/托福 = 生词候选 |
| 复习算法 | SM-2 简化版(间隔重复);连认 4 次或间隔 ≥21 天 = 毕业移出 |
| 卡片 | 正面词+音标+🔊发音(Web Speech API);翻面中文释义 + 原文例句(标来源) |

## 2. 架构(方案 A:静态页 + 构建期词库)

```
电脑(一次性/每次新增文章后)                     手机(日常)
┌──────────────────────────┐              ┌──────────────────────┐
│ build.py                  │              │ /script/vocab/ 静态页  │
│  60 篇 md ──提取英文──┐    │   upload.py  │  index.html/app.js/    │
│  ECDICT csv ──────────┼─→ │ ──────────→ │  core.js/style.css +   │
│  词形归并/划线/配例句   ↓    │  vocab.json │  vocab.json            │
│                     vocab.json│         │  状态=localStorage      │
└──────────────────────────┘              │  导出/导入 JSON 备份    │
                                          └──────────────────────┘
```

- 词池数据在构建期固化进 `vocab.json`(几百 KB),前端零计算负担
- 手机端进度按"词"存,词池更新(重传 vocab.json)不丢进度;新词自动进入队列
- 无后端、无数据库;部署 = scp 静态文件

## 3. 组件设计

### 3.1 词池构建 `tools/vocab-review/build.py`

输入:`--src`(默认取 subtitle-viewer config.json 的 src_root)+ `--ecdict`(ECDICT
主 CSV 路径;首次需从 GitHub skywind3000/ecdict 下载解压,约 190MB,脚本缺失时打印
下载指引)。

流程(纯函数化,便于 pytest):

1. **收词**:遍历 src_root 下含时间戳的 md,取 `**英文**` 行;token 化(小写、去
   标点);跳过纯数字、单字母、含数字/符号的 token
2. **词形归并**:用 ECDICT `exchange` 字段构建 变体→原形 映射(running/runs/ran →
   run);查不到映射的保持原样
3. **过滤**:ECDICT 未收录且词频为 0 的词丢弃(多为 Whisper 误识/专名);在原文中
   始终首字母大写的专名跳过
4. **划线**(`--level` 参数,默认 `gk`):
   - tags 含 `zk`(中考)或 `gk`(高考)→ **默认已会**(不进卡片,计入统计)
   - 含 `cet4/cet6/ky/toefl/ielts/gre` → **生词候选**
   - 无标签但 COCA 词频排名前 5000 → 默认已会(常用词兜底)
   - 其余 → 生词候选
5. **例句**:每候选词从原文英文句中选最多 2 条(优先 5-20 词、含该词任意词形的
   句子),记录来源文档标题
6. **产出** `web/vocab.json`:`{version, generated_at, words:[{w, phon, def, tags,
   level, sents:[{en, from}]}], stats:{total, known, candidate, dropped}}` + 终端报告

### 3.2 前端 `tools/vocab-review/web/`

- `core.js`(纯逻辑,node --test 可测):SM-2 状态机、每日队列生成、状态存取/
  导出导入合并
- `app.js` + `index.html` + `style.css`:按已确认设计稿(390px 手机优先,浅底紫
  主色,与字幕站一致)
- 界面:统计条(总池/待复习/今日队列/已毕业)→ 今日进度条 → 卡片区(正面/翻面)
  → 判定双按钮 → ⚙设置(每日新词上限默认 20、导出/导入)
- 发音:`speechSynthesis`(en-US, rate 0.9),点词或 🔊 触发
- 键盘(电脑辅助):空格翻面,← 不认识 / → 认识

### 3.3 SM-2 简化版(状态与规则)

每词状态(localStorage,按词形原形为键):
`{e: ease(初始 2.5), i: interval 天, r: reps 连认次数, due: 时间戳, g: graduated}`

| 动作 | 状态转移 |
|---|---|
| 认识 | r+=1;i = r==1 ? 1 : r==2 ? 3 : round(i×e);due=now+i 天;r≥4 或 i≥21 → g=true(毕业,永久不再入队) |
| 不认识 | r=0;i=0;e=max(1.3, e−0.2);due=now+10 分钟(会话内隔 10 张重现,次日正常入队) |

**每日队列**(打开页面时计算,当日缓存):到期复习词(due ≤ 今天且未毕业,排前)
+ 新词(无状态,补足每日上限,默认 20,排后)。不认识的卡重新插入当前位置 +10。
每日新词计数持久化(`last_new_date/last_new_count`),跨会话不超发。

### 3.4 部署与入口

- `tools/vocab-review/upload.py`:scp `web/` 四文件 + `vocab.json` →
  `47.108.230.162/script/vocab/`(复用 sync_subtitles 的 ssh 方式)
- 字幕站顶栏加「🔤 单词复习」入口链接(改 subtitle-viewer index.html 一行)
- 线上地址:http://47.108.230.162/script/vocab/

### 3.5 增长与兼容

新增文章 → 电脑重跑 `build.py` + `upload.py` → 手机端 vocab.json 变新、进度状态
保留;已毕业词仍在池中但 g=true 不再出现;文章删除导致词消失 → 端上多余状态无害。

## 4. 错误处理

| 场景 | 行为 |
|---|---|
| vocab.json 加载失败 | 错误提示页(检查网络/是否已上传) |
| localStorage 不可用(隐私模式) | 顶部横幅警告"进度不会保存",功能仍可用 |
| 导入文件损坏/结构不对 | 校验失败提示,原状态不动 |
| ECDICT 缺词/怪词 | 构建期丢弃并计入报告 dropped |
| 例句找不到(词只出现在标题等) | 该词无例句,卡片仍可用 |

## 5. 测试

- `tests/test_vocab_build.py`(pytest,离线):token 提取、exchange 归并、划线分类、
  例句选择、stats 统计 —— 用小 fixture md + 迷你 ECDICT CSV fixture
- `web/core.test.js`(node --test):SM-2 转移(认识/不认识/毕业)、每日队列与上限、
  导出导入合并

## 6. 非目标(YAGNI)

跨设备云同步、多用户、欧路 API/MCP 联动、挖空卡模式、真人发音音频文件、后端服务。
