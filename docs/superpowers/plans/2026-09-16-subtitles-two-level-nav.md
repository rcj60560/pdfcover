# 字幕站两级导航网格 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `/script/subtitles/` 改为「书目网格 → 书内 Unit 网格」两级导航,卡片完整显示名称。

**Architecture:** manifest 数据结构不动;前端 `core.js` 新增纯函数 `groupBooks()` 聚合书目,`app.js` 路由加 `?book=` 一级,两级都渲染网格卡片。

**Tech Stack:** 原生 ES module + node:test + pytest(回归)。

**Spec:** `docs/superpowers/specs/2026-09-16-subtitles-two-level-nav-and-cambridge-vocab-pipeline-design.md`(需求 A 节)

## Global Constraints

- 字幕 md 格式与 `subtitle_lib.py` 的 `TS_RE`、`core.js` 的 `TS_RE` 保持不变。
- 缓存版本号统一升 v=8:`index.html` 的 style.css/app.js 引用 + `app.js` 内 `core.js?v=` import,三处同步。
- 提交前 `node --test` 与 `pytest tests/test_subtitle_viewer.py` 全绿。
- 根目录散文档的书名显示为「其他」。

---

### Task 1: `groupBooks()` 纯函数

**Files:**
- Modify: `tools/subtitle-viewer/core.js`(文件末尾追加)
- Test: `tools/subtitle-viewer/core.test.js`

**Interfaces:**
- Produces: `groupBooks(docs) -> [{dir: string, count: number, duration: number}]`,dir 为目录名(根目录文档 dir 为 "其他"),按 dir 升序;count/duration 为该书合计。manifest 的 doc 字段:`{path, title, count, duration}`(秒)。

- [ ] **Step 1: 写失败测试**(追加到 core.test.js 末尾;import 行加入 `groupBooks`)

```js
test("groupBooks 按书聚合数量与时长,根目录归其他", () => {
  const books = groupBooks([
    { path: "in-use/Unit 1.md", title: "Unit 1", count: 3, duration: 20 },
    { path: "in-use/Unit 2.md", title: "Unit 2", count: 2, duration: 14 },
    { path: "root.md", title: "root", count: 1, duration: 6 },
  ]);
  assert.deepEqual(
    books.map((b) => [b.dir, b.count, b.duration]),
    [["其他", 1, 6], ["in-use", 5, 34]],
  );
  assert.deepEqual(groupBooks([]), []);
});
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd tools/subtitle-viewer && node --test`
Expected: FAIL,`groupBooks is not defined`(或 import 报错)

- [ ] **Step 3: 最小实现**(core.js 末尾,紧跟 `groupManifest` 之后)

```js
export function groupBooks(docs) {              // 一级书目:按目录聚合篇数与总时长
  const map = new Map();
  for (const d of docs) {
    const dir = d.path.includes("/") ? d.path.slice(0, d.path.lastIndexOf("/")) : "";
    if (!map.has(dir)) map.set(dir, { dir, count: 0, duration: 0 });
    const b = map.get(dir);
    b.count += d.count;
    b.duration += d.duration;
  }
  return [...map.values()]
    .sort((a, b) => a.dir.localeCompare(b.dir, "zh-CN"))
    .map((b) => ({ ...b, dir: b.dir || "其他" }));
}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd tools/subtitle-viewer && node --test`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add tools/subtitle-viewer/core.js tools/subtitle-viewer/core.test.js
git commit -m "feat(subtitle-viewer): groupBooks 书目聚合纯函数"
```

---

### Task 2: 两级路由 + 网格渲染 + 样式

**Files:**
- Modify: `tools/subtitle-viewer/app.js`(列表视图区、路由区)
- Modify: `tools/subtitle-viewer/index.html`(版本号 v=8)
- Modify: `tools/subtitle-viewer/app.js` 内 `from "./core.js?v=..."`(同步 v=8)
- Modify: `tools/subtitle-viewer/style.css`(网格样式)

**Interfaces:**
- Consumes: Task 1 的 `groupBooks(docs)`;既有 `groupManifest(docs)`、`formatMs(ms)`、`esc(s)`。
- Produces: 路由三态——无参数(书目网格)/`?book=<dir>`(书内网格)/`?doc=<path>`(原文档视图,不动)。

- [ ] **Step 1: app.js 列表视图改造**

`loadManifest` 与 `renderList` 整体替换为(注意 `groupBooks` 加入顶部 import):

```js
async function loadManifest() {
  let manifest = { docs: [] };
  try {
    const res = await fetch("manifest.json", { cache: "no-store" });   // 列表必须拿最新（浏览器启发式缓存会赖着旧 manifest）
    if (res.ok) manifest = await res.json();
  } catch { /* 网络失败 → 空列表提示 */ }
  const docs = manifest.docs || [];
  const book = new URLSearchParams(location.search).get("book");
  if (book) renderUnits(docs, book);
  else renderBooks(docs);
}

function gridCard(href, title, meta) {
  return `<a class="card" href="${href}">` +
    `<span class="card-title">${esc(title)}</span>` +
    `<span class="card-meta">${meta}</span></a>`;
}

function renderBooks(docs) {
  const books = groupBooks(docs);
  $("#app-title").textContent = "字幕跟读器";
  if (!books.length) {
    $("#list").innerHTML =
      `<p class="empty">还没有字幕。先在电脑上跑 <code>python sync_subtitles.py</code> 上传。</p>`;
    return;
  }
  $("#list").innerHTML = `<div class="grid">` + books.map((b) =>
    gridCard(location.pathname + "?book=" + encodeURIComponent(b.dir),
      b.dir, `${b.count} 篇 · ${formatMs(b.duration * 1000)}`)).join("") + `</div>`;
}

function renderUnits(docs, book) {
  const items = docs.filter((d) =>
    d.path.startsWith(book + "/") ||
    (book === "其他" && !d.path.includes("/")));
  const title = items.length ? book : "没有这本书";
  $("#app-title").textContent = title;
  $("#back").hidden = false;
  $("#back").textContent = "‹ 书库";
  $("#list").innerHTML = items.length
    ? `<div class="grid">` + items.map((d) =>
        gridCard(location.pathname + "?doc=" + encodeURIComponent(d.path),
          d.title, `${d.count} 条 · ${formatMs(d.duration * 1000)}`)).join("") + `</div>`
    : `<p class="empty">这本书还没有字幕。</p>`;
}
```

- [ ] **Step 2: 返回按钮行为**

既有 `$("#back").addEventListener("click", () => { location.href = location.pathname; })` 行为(回站点根)对书内页恰好正确(根=书目网格),不改。但文档页的返回应回**所属书**而不是书目网格——将 `openDoc` 里 `location.href = location.pathname;` 的错误回退与 `#back` 点击处理保持现状(回书目根),可接受,不动。

- [ ] **Step 3: 样式(style.css 列表区追加)**

```css
/* 两级网格 */
#list .grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }
@media (min-width: 640px) { #list .grid { grid-template-columns: repeat(3, 1fr); } }
.card {
  display: flex; flex-direction: column; gap: 8px; min-height: 96px;
  padding: 14px; border-radius: 12px;
  background: var(--card); color: var(--fg); text-decoration: none;
}
.card-title { font-size: 14px; font-weight: 600; line-height: 1.45; overflow-wrap: anywhere; }
.card-meta { font-size: 12px; color: var(--muted); margin-top: auto; }
```

- [ ] **Step 4: 版本号升 v=8**

`index.html`:`style.css?v=7` → `?v=8`,`app.js?v=7` → `?v=8`;`app.js` import:`./core.js?v=7` → `?v=8`。

- [ ] **Step 5: 验证**

```bash
cd tools/subtitle-viewer && node --check app.js && node --test
cd ../../ && python -m pytest tests/test_subtitle_viewer.py -q
python tools/subtitle-viewer/dev_server.py &   # 或后台
curl -s http://127.0.0.1:8800/ | grep -c 'class="grid"'
curl -s "http://127.0.0.1:8800/?book=in-use-advanced" -o /dev/null -w "%{http_code}\n"   # 200(SPA 由前端渲染)
```
浏览器肉眼验收:一级两列卡片、点进二级网格、卡片名称完整两行内、`?doc=` 正常。

- [ ] **Step 6: Commit**

```bash
git add tools/subtitle-viewer/app.js tools/subtitle-viewer/index.html tools/subtitle-viewer/style.css
git commit -m "feat(subtitle-viewer): 两级导航——书目网格与书内 Unit 网格"
```

---

### Task 3: README + 同步公网

**Files:**
- Modify: `tools/subtitle-viewer/README.md`

- [ ] **Step 1: README 更新**

首段「选对应字幕 MD」前补一句:「列表为两级:书目网格 → 书内 Unit 网格(`?book=`)。」

- [ ] **Step 2: 同步并验证公网**

```bash
cd tools/subtitle-viewer && python sync_subtitles.py
curl -s http://47.108.230.162/script/subtitles/ | grep -c 'v=8'
curl -s http://47.108.230.162/script/subtitles/app.js | grep -c 'renderBooks'
```

- [ ] **Step 3: Commit**

```bash
git add tools/subtitle-viewer/README.md
git commit -m "docs(subtitle-viewer): 两级导航说明"
```
