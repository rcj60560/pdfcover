# B站字幕工具 · 批量模式设计

> 2026-11-17 定稿。需求来源:Reading Explorer 216 集这类大合集,用户只想精翻其中若干集,
> 现有单集流程(拉取→分段复制→词典翻译→粘贴→排版)要逐集手动发起,批量模式把「拉英文」环节自动化。
> 状态:**设计已批准,待写实施计划**。

## 一、场景与目标

用户贴一个多 P 合集链接(如 BV1gK4y1o7Ni,216 集 Reading Explorer):

1. 工具枚举全部分 P(标题/时长),用户**勾选**需要的集数(支持全选、范围输入如 `1-10,15`)
2. 后端顺序批量拉取英文(现有单集管线,含 Whisper 与转写缓存)
3. 每集完成后产出独立 job,批量页「去处理」跳进**现有阅读页**,照旧:复制分段 → 欧路翻译 → 粘贴 → 排版 → 下载 md
4. 翻译与排版环节**保持现状逐集手动**(方案 A),批量只自动化拉取

**约束**(用户明示):网络不稳要有兜底;能正常拉到英文;**不能被 B 站限流**;时间不敏感,可挂机慢跑。

## 二、架构(纯加法)

- `app.py`:新增 Batch/BatchItem 数据结构、5 个 API、1 个队列线程
- `templates/index.html` + `static/app.js`:首页加「批量模式」面板(idle→listing→ready→running 状态机,3s 轮询)
- 枚举:B 站 view API `api.bilibili.com/x/web-interface/view?bvid=<bv>` **一次请求**返回 `data.pages[].{page,part,duration}`,经 curl_cffi chrome131(复用 extractor 现有指纹链路与重试)
- 单集管线(extractor / direct_generate / 阅读页 / 排版)**零改动**

## 三、数据结构与断点续跑

```python
@dataclass
class BatchItem:
    p: int                # 分P号(1 起)
    title: str            # 枚举时拿到的集标题
    duration: int         # 秒
    status: str           # queued | running | done | failed
    job_id: str | None    # 完成后关联单集 job(「去处理」入口)
    error: str            # 失败原因(最近一次)
    attempts: int         # 已尝试次数

@dataclass
class Batch:
    batch_id: str         # 随机 hex
    source_url: str       # 归一化后的 BV 链接
    title: str            # 系列名(枚举返回的 video title)
    items: list[BatchItem]
    interval_sec: int     # 集间固定间隔,默认 60
    state: str            # running | finished
    created_at: str
```

- **落盘**:每次条目状态变更把批次 JSON 写 `outputs/batch/<batch_id>.json`(原子写:先 tmp 后 rename)
- **恢复**:启动时扫描 `outputs/batch/*.json` 载入;`running` 条目回 `queued`;`state=running` 的批次在批量页标「可恢复」,用户点恢复才重起队列线程(不自动跑)——已完成集走转写缓存秒回
- **不做暂停按钮**(YAGNI):失败自动退避,停服务=自然暂停

## 四、队列逻辑(防限流三件套)

单队列线程顺序处理 `status=queued` 的条目:

```
for item in 待处理:
    item.status = running → 落盘
    try:
        result = generate_rows_from_audio(source_url + "?p=" + item.p)   # 现有管线
        job = 挂进 JOBS(items 的 rows 复用现有 Job 结构)
        item.job_id, item.status = done
    except Exception as e:
        item.attempts += 1; item.error = str(e)
        若 attempts < 3:状态回 queued,sleep(退避) 后重试当前集
             退避 = 60s × 5^(attempts-1),上限 15 分钟
        否则:status = failed,继续下一集
    落盘
    if 还有下一集: sleep(interval_sec)
全部结束 → batch.state = finished → 落盘
```

- 退避期间的 sleep 在队列线程内,不阻塞 Flask
- 网络抖动的**集内**重试由现有管线负责(extractor 的 chrome131 切换 + flushdns 链;download_audio 同款);队列层只管**集间**节奏
- 同一 P 重复执行幂等(转写缓存命中秒回)
- 全选超过 30 集时前端弹确认框,估算耗时 = Σ(单集时长/4 转写估速 + 集间隔)(small.en CPU 实测约 3.8× 实时速,取 4 保守)

## 五、API(5 个)

| 接口 | 入 | 出 | 说明 |
|---|---|---|---|
| POST `/api/batch/list` | `{url}` | `{ok, title, items:[{p,title,duration}]}` | 纯预览,不建批;view API 一次调用 |
| POST `/api/batch/start` | `{url, ps:[int], interval}` | `{ok, batch_id}` | 建批+落盘+起线程 |
| GET `/api/batch/list` | — | `{ok, batches:[摘要]}` | 已有批次(含可恢复) |
| GET `/api/batch/<id>` | — | `{ok, batch 全量}` | 前端轮询 |
| POST `/api/batch/<id>/retry` | `{p}` | `{ok}` | 单集状态置 queued;若批次已 finished 则重启线程 |

错误口径:枚举失败返回可读信息(网络/链接无效),沿用现有 `_friendly_error` 风格。

## 六、前端批量面板

首页现有单集面板下方新增(默认折叠 `<details>`,避免干扰单集动线):

1. **idle**:链接输入框 + 「列出集数」
2. **listing→ready**:集数列表(每行 checkbox + p 号 + 截断标题 + 时长);顶部「全选/清空」+ 范围输入(`1-10,15`)+「按范围勾选」;集间隔数字输入(默认 60)+ 已选计数 + 「开始批量」(>30 集确认框)
3. **running**:总进度条(完成/总数)+ 表格(每行:p/标题/状态徽章 排队⏳/进行中🔄/完成✅/失败❌/「去处理」(done 时,跳该 job 阅读视图)/「重试」(failed 时));3s 轮询,全部完成停止轮询(BatchItem 不细分下载/转写子阶段,进行中即够用)
4. **恢复**:页面加载时拉批次列表,非 finished 批次显示「恢复」按钮

「去处理」复用现有阅读页渲染函数:按 job_id 取预览数据进入阅读视图(与单集流程同一入口,实施时对齐 app.js 现有 render 调用)。

## 七、顺带小修(独立提交,不阻塞批量)

1. `alignment_agent.run_claude_align` 超时改**杀进程树**(Windows: `taskkill /F /T /PID`;修 cmd 壳死、node 成孤儿的 bug)
2. headless 排版固定快档:`claude -p` 加模型/推理档参数,不跟随用户全局 max 设置(参数实施时验证 CLI 支持,目标机械切分 1-2 分钟内完成)

## 八、测试策略

| 层 | 内容 |
|---|---|
| 纯逻辑单测 | 范围解析(`1-10,15`/乱序/越界)、view API 响应→items 解析、批次落盘/加载 roundtrip(running→queued)、退避时长计算 |
| 队列线程 | monkeypatch `generate_rows_from_audio`(不触网不跑 Whisper):成功流/失败重试 3 次/跳过继续/间隔与退避的 sleep 被正确调用(mock sleep) |
| API | Flask test client:枚举(mock 网络)/start/详情/retry 状态流转 |
| 真机验收 | Reading Explorer 勾 3 集:p6、p7(已缓存→秒回验证)+ 1 新集(全链);断服务重启→恢复批次 |

## 九、不做(YAGNI)

自动机翻、批量排版自动化、暂停/限速调节 UI、合集(多 BV)支持、并发转写(单 Whisper 已吃满 CPU)。
