# vocab-review 实现全记录

> 2026-09-29 整理。功能定位:个人雅思词汇复习工具——把字幕文章库变成词池,SM-2 间隔复习,公网手机优先。
> 设计为独立可迁移:纯静态前端 + 纯逻辑层分离,后端只在"构建期"存在。

## 一、整体数据流

```
【内容层】用户的字幕文章库(hcrs_devdocs/ielts/ 下带时间戳的双语 md,~60 篇,持续新增)
    │
    ▼ build.py(电脑端,Python 纯标准库)
【词典层】ECDICT sqlite(tmp/ecdict/stardict.db,811MB,340万词条)
    │         + 雅思词书(tmp/kajweb/*.json,有道/新东方,JSONL)
    ▼
vocab.json(词池快照:候选词+释义+例句+统计,~900KB)
    │ upload.py(scp)
    ▼
【展示层】公网静态站 /script/vocab/(主)/ /script/vocab-beta/(增强预览)
    手机端 SM-2 状态存 localStorage,导出/导入 JSON 备份
```

构建期与运行期完全分离:**页面上线后零后端依赖**,换词典/换前端互不影响。

## 二、组件清单(全部在 tools/vocab-review/)

| 文件 | 职责 | 关键接口 |
|---|---|---|
| `ecdict.py` | ECDICT sqlite 只读查询 | `load_for_tokens(db, tokens) -> (entries, lemmas)`;词形原形只取 exchange `0:` 段(`1:` 是形态代码,误用出垃圾卡,有回归测试) |
| `build.py` | 词池构建管线 + CLI | `md_english_lines/doc_title/tokenize/split_sentences/classify/pick_sentences/build/main` |
| `enrich.py` | 雅思词书增强层(可选) | `enrich(vocab, books) -> (vocab, count)`,加可选字段 enDef/phrases/ydSents |
| `web/core.js` | **纯逻辑层(可迁移核心)** | SM-2 全套:`newState/answerYes/answerNo/endOfToday/buildQueue`;存储:`STORAGE_KEY/emptyBox/mergeImport/loadState/saveState/exportPayload`;统计:`logJudge/summarize`;总览:`wordGroups` |
| `web/app.js` | UI 编排(DOM) | 卡片直显/判定/发音/回看/搜索+详情/总览/统计/设置/重置/继续复习 |
| `web/index.html` + `style.css` | 结构与 Discord 浅色皮肤 | 390px 手机一屏化(100dvh 锁视口,卡片内滚,按钮常驻) |
| `upload.py` | 部署 | `--dir vocab|vocab-beta` `--vocab 文件`,ssh mkdir→scp→chown |

测试:`tests/test_vocab_review.py`(220 pytest,含 ecdict/build/enrich 纯逻辑)+ `web/core.test.js`(10 node --test,SM-2/队列/导入导出/分组)。

## 三、核心规则(全部有测试锁定)

### 划线(谁是分母)
- 全语料收词 → ECDICT 词形归并(running/runs/ran → run)
- 标签 `zk`(中考)/`gk`(高考) → **已会**(不进卡片)
- 标签 `cet4/cet6/ky/toefl/ielts/gre` → **生词候选**
- 无标签但 COCA 词频排名 ≤5000 → 已会;`frq=0`(未入语料) → 丢弃
- 附加丢弃:≤3 字母非已会(don/t/s)、全大写≤5字母无标签(BBC)、**全文从未小写出现且无标签**(John/Rafael 等人名)
- 例句:取自用户文章,最长优先 2 条,带来源

### SM-2(记忆曲线)
- 状态 `{e:2.5, i:间隔天, r:连认, due, g:毕业}`,键=词形原形
- 认识:r+1,i=1→3→round(i×e);**r≥4 或 i≥21 → 毕业永久移出**
- 不认识:e−0.2(下限1.3),r/i 清零,due=+10min,**当前队列隔 10 张重现**
- 每日队列 = 到期复习(due≤今日末,按 due 升序) + 新词(每日上限,默认20,跨会话记账不超发)
- 「继续复习」= 用户显式意图,直接追加一批未发新词(不走限额扣减),照常记账
- 判定即落库;统计日志 dailyLog{日期:{y,n}} + 累计正确率,近 7 天趋势

### 存储(手机端)
- `vocab-review-state-v1`:{states:{词:状态}, meta:{lastNewDate/lastNewCount/dailyLog/totalYes/totalNo}}
- `vocab-review-settings-v1`:{dailyLimit}
- 导出=JSON 下载;**导入=整体覆盖**(不是合并);重置=删 state 键
- ⚠️ rebuildQueue 用 `...box.meta` 展开保留旧字段(整体替换会清统计日志——修过的 bug)

## 四、增强层(雅思词书)
- 数据:kajweb/dict(有道背单词爬取)IELTSluan_2(有道3427词)+IELTS_3(新东方3575词),JSONL
- 下载通道:**api.github.com 直连可达**(github.com/raw 被墙),blobs API + `Accept: application/vnd.github.raw`
- enrich 规则:词池∩词书(约 41%,617 词)加可选字段:enDef(英英,跨书去重)、phrases(top3)、ydSents(top2 双语例句,有道书优先);不动既有字段与顺序
- UI 可选渲染(字段缺失不显示),向后兼容 → 主站/beta 共用同一 app,仅 vocab.json 不同

## 五、运维节奏
- 新增文章:`python build.py`(自动扫 src_root 全部 md)→ `python enrich.py`(增强)→ `python upload.py`(主站)→ `python upload.py --dir vocab-beta --vocab web/vocab-beta.json`(beta)
- 手机进度不受词池更新影响(按词键存);文章删除导致词消失→端上孤儿状态无害

## 六、已知边界/遗留
- 人名过滤误伤 ~7 个句首大写普通词(firstly/luckily 等)——用户裁定:不关键,不修
- 待复习/今日队列显示同值;开页即烧当日新词配额;统计瓦片口径(全量 vs 卡片);冷加载按钮闪现——均记录未修
- ECDICT `1:i` 类 exchange 怪癖致极个别噪声 lemma(2/1521)
- 有道数据版权:自用学习,公网部署自担(仓库有下架声明)

## 七、迁移要点(如果做 App/小程序)
- **可直接搬走**:`core.js`(纯逻辑,零 DOM 依赖,带测试)——SM-2/队列/存储/统计全在里面;`build.py/ecdict.py/enrich.py`(构建期,换端不动;产物 vocab.json 通用)
- **需要重写**:app.js(DOM)→ 目标端 UI(WXML/Compose/React Native…);style.css
- **语音**:Web 用 speechSynthesis;小程序用"微信同声传译"插件;App 用系统 TTS
- **存储升级路径**:localStorage → 云数据库(微信云开发/任一 BaaS)可获得跨设备同步;字段结构现成
