/** vocab-review 复习页:加载词库 → 建队列 → 卡片流(直显/判定/发音/回看)+ 统计报表 + 词库总览 + 设置抽屉。纯逻辑在 core.js。 */
import {
  newState, answerYes, answerNo, buildQueue,
  mergeImport, loadState, saveState, exportPayload, logJudge, summarize, wordGroups,
  STORAGE_KEY,
} from "./core.js";

const SETTINGS_KEY = "vocab-review-settings-v1";
const $ = (id) => document.getElementById(id);

/* ---------- 全局状态 ---------- */
let vocab = null;            // vocab.json 全文
let vocabIndex = new Map();  // w → 词条
let box = null;              // 进度盒 {states, meta}
let settings = { dailyLimit: 20 };
let queue = [];              // 今日队列(队首 = 当前卡)
let judged = 0;              // 本次会话已判定张数(进度条分子)
let reviewed = 0;            // 本次会话判定的复习张数
let fresh = 0;               // 本次会话判定的新词张数
let history = [];            // 本会话已判定的词(按判定顺序,供回看)
let viewIndex = 0;           // 0 = 当前卡;i > 0 = 只读回看倒数第 i 张
let statsOpen = false;       // 统计报表是否打开
let listOpen = false;        // 词库总览是否打开
let listFilter = { q: "", status: "all" };  // 总览筛选:搜索串 + 状态(默认全部)
const classified = new Set(); // 已计数的词(不认识的卡重现时不重复计数)
let toastTimer = 0;

const canSpeak = typeof window !== "undefined" && "speechSynthesis" in window;

/* ---------- 小工具 ---------- */
const fmt = (n) => n.toLocaleString("zh-CN");
const hasState = (w) => Object.prototype.hasOwnProperty.call(box.states, w);

function toast(msg) {
  const el = $("toast");
  el.textContent = msg;
  el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), 2000);
}

function speak(text) {
  if (!canSpeak) return;
  try {
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = "en-US";
    u.rate = 0.9;
    window.speechSynthesis.speak(u);
  } catch { /* 发音失败不影响复习 */ }
}

/* ---------- 设置(独立于进度存 localStorage) ---------- */
function loadSettings() {
  try {
    const raw = localStorage.getItem(SETTINGS_KEY);
    if (raw) {
      const n = JSON.parse(raw).dailyLimit;
      if (Number.isFinite(n) && n >= 1) return { dailyLimit: Math.round(n) };
    }
  } catch { /* 读不到就用默认 */ }
  return { dailyLimit: 20 };
}

function saveSettings() {
  try { localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings)); } catch { /* 隐私模式 */ }
}

/* ---------- 统计 / 进度 ---------- */
function renderStats() {
  const st = vocab.stats || {};
  $("stTotal").textContent = fmt((st.candidate || 0) + (st.known || 0) || vocab.words.length);
  $("stDue").textContent = fmt(queue.length);
  $("stToday").textContent = fmt(queue.length);
  $("stGrad").textContent = fmt(Object.values(box.states).filter((s) => s && s.g).length);
}

function renderProgress() {
  const total = judged + queue.length; // 分母含「不认识」的重现卡,队列清空时恰为 100%
  const pct = total ? Math.min(100, Math.round((judged / total) * 100)) : 0;
  $("progText").textContent = `今日 ${judged}/${total}`;
  $("progPct").textContent = `${pct}%`;
  $("barFill").style.width = `${pct}%`;
}

/* ---------- 卡片渲染 ---------- */
function escapeReg(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"); }

/** 例句内高亮目标词:词边界正则,大小写不敏感 */
function fillSentence(p, text, word) {
  const re = new RegExp(`\\b${escapeReg(word)}\\b`, "gi");
  let last = 0, m;
  while ((m = re.exec(text)) !== null) {
    p.append(text.slice(last, m.index));
    const hit = document.createElement("span");
    hit.className = "hit";
    hit.textContent = m[0];
    p.append(hit);
    last = m.index + m[0].length;
  }
  p.append(text.slice(last));
}

function renderCard() {
  const readonly = viewIndex > 0;
  const w = readonly ? history[history.length - viewIndex] : queue[0];
  const item = vocabIndex.get(w) || { phon: "", def: "", tags: "", sents: [] };
  $("src").textContent = readonly ? "回看 · 只读,不计分"
    : (hasState(w) ? "复习 · 到期重现" : "生词候选 · 来自词池");
  $("word").textContent = w;
  $("phon").textContent = [item.phon, item.tags].filter(Boolean).join(" · ");
  $("def").textContent = item.def || "";
  const exs = $("exs");
  exs.textContent = "";
  for (const sent of (item.sents || []).slice(0, 2)) {
    const ex = document.createElement("div");
    ex.className = "ex";
    const p = document.createElement("p");
    fillSentence(p, sent.en || "", w);
    const from = document.createElement("span");
    from.className = "from";
    from.textContent = `📖 ${sent.from || ""}`;
    ex.append(p, from);
    exs.append(ex);
  }
  // 回看导航
  $("nav").hidden = history.length === 0;
  $("prevBtn").disabled = viewIndex >= history.length;
  $("nextBtn").disabled = viewIndex === 0;
  $("navInfo").textContent = readonly ? `回看 ${viewIndex}/${history.length}` : "";
  // 判定只在当前卡可用
  $("btnNo").disabled = readonly;
  $("btnYes").disabled = readonly;
}

/* ---------- 卡片流 ---------- */
function judge(yes) {
  if (viewIndex !== 0 || !queue.length) return;
  const w = queue.shift(); // 当前卡出队
  const now = Date.now();
  if (!classified.has(w)) { classified.add(w); hasState(w) ? reviewed++ : fresh++; }
  box.meta = logJudge(box.meta, now, yes); // 每次判定记账(当日/累计/趋势)
  const next = (yes ? answerYes : answerNo)(box.states[w] || newState(), now);
  box.states[w] = next;
  saveState(box); // 判定即落盘
  if (next.g) toast(`🎓 ${w} 毕业!`); // 队列里的词必非毕业态,next.g 即刚毕业
  if (!yes) queue.splice(Math.min(10, queue.length), 0, w); // 隔 10 张重现,至多插到队尾
  history.push(w);
  judged++;
  render();
}

function lookBack() {          // ◀ 只读回看上一张
  if (viewIndex >= history.length) return;
  viewIndex++;
  renderCard();
}

function returnNow() {         // ▶ 返回当前卡
  if (viewIndex === 0) return;
  viewIndex = 0;
  renderCard();
}

function render() {
  renderStats();
  renderProgress();
  $("done").hidden = true;
  $("error").hidden = true;
  if (searchQ) { renderSearch(); return; }   // 检索态:不展示卡片/完成屏
  $("searchView").hidden = true;
  if (!queue.length) { showDone(); return; }
  $("flash").hidden = false;
  $("judge").hidden = false;
  $("hint").hidden = false;
  renderCard();
}

/* ---------- 顶部本地检索:输入即搜全词池 ---------- */
let searchQ = "";
const SEARCH_MAX = 30;

function statusOf(w) {
  const s = box.states[w];
  return s ? (s.g ? "done" : "learning") : "fresh";
}

function renderSearch() {
  const q = searchQ.toLowerCase();
  const matches = vocab.words.filter((x) => x.w.toLowerCase().includes(q));
  hideCardArea();
  $("done").hidden = true;
  $("error").hidden = true;
  $("searchCount").textContent = matches.length
    ? `「${searchQ}」共 ${fmt(matches.length)} 个匹配${matches.length > SEARCH_MAX ? ` · 显示前 ${SEARCH_MAX} 个` : ""}`
    : `「${searchQ}」没有匹配的单词`;
  const list = $("searchList");
  list.textContent = "";
  const frag = document.createDocumentFragment();
  for (const x of matches.slice(0, SEARCH_MAX)) {
    const row = document.createElement("div");
    row.className = "lv-row";
    row.addEventListener("click", () => speak(x.w));
    const main = document.createElement("div");
    main.className = "lv-main";
    const wordBtn = document.createElement("button");
    wordBtn.type = "button";
    wordBtn.className = "lv-word";
    wordBtn.textContent = x.w;
    const def = document.createElement("div");
    def.className = "lv-def";
    def.textContent = [x.phon, x.def].filter(Boolean).join(" · ");
    main.append(wordBtn, def);
    const tag = document.createElement("span");
    const st = statusOf(x.w);
    tag.className = `lv-tag ${st}`;
    tag.textContent = LV_LABEL[st];
    row.append(main, tag);
    frag.append(row);
  }
  list.append(frag);
  $("searchView").hidden = false;
}

$("homeSearch").addEventListener("input", (e) => {
  searchQ = e.target.value.trim();
  render();
});
$("homeSearch").addEventListener("keydown", (e) => {
  if (e.key === "Escape") { e.target.value = ""; searchQ = ""; render(); }
});

function hideCardArea() {
  $("flash").hidden = true;
  $("judge").hidden = true;
  $("nav").hidden = true;
  $("hint").hidden = true;
}

function showDone() {
  hideCardArea();
  $("doneCount").textContent = `复习 ${reviewed} · 新词 ${fresh}`;
  // 词池里还有未发出的新词时才提供「继续复习」
  const issued = Object.keys(box.states).length;
  $("doneMore").hidden = vocab.words.length - issued <= 0;
  $("done").hidden = false;
}

function showError() {
  hideCardArea();
  $("error").hidden = false;
}

/* ---------- 统计报表 ---------- */
function renderChart(trend) {
  const chart = $("svChart");
  chart.textContent = "";
  const H = 72; // 最大柱高(px)
  const max = Math.max(1, ...trend.map((d) => d.y + d.n));
  for (const d of trend) {
    const col = document.createElement("div");
    col.className = "col";
    const segs = [];
    for (const [cls, v] of [["yes", d.y], ["no", d.n]]) {
      if (!v) continue;
      const seg = document.createElement("i");
      seg.className = `seg ${cls}`;
      seg.style.height = `${Math.max(3, Math.round((v / max) * H))}px`;
      segs.push(seg);
    }
    if (segs.length) segs[0].classList.add("top"); // 数据端圆角
    const label = document.createElement("span");
    label.className = "col-label";
    const [, mm, dd] = d.key.split("-");
    label.textContent = `${Number(mm)}/${Number(dd)}`;
    col.title = `${d.key}:认识 ${d.y} · 不认识 ${d.n}`;
    col.setAttribute("aria-label", `${Number(mm)}月${Number(dd)}日:认识 ${d.y},不认识 ${d.n}`);
    col.append(...segs, label);
    chart.append(col);
  }
}

function openStats() {
  if (!vocab || !box) return;
  statsOpen = true;
  hideCardArea();
  $("done").hidden = true;
  $("listView").hidden = true; // 整卡画面互斥:总览开着时切到统计
  listOpen = false;
  const s = summarize(vocab.words.map((x) => x.w), box.states, box.meta, vocab.stats);
  $("svTotal").textContent = fmt(s.total);
  $("svGrad").textContent = fmt(s.graduated);
  $("svLearn").textContent = fmt(s.learning);
  $("svNew").textContent = fmt(s.notStarted);
  $("svToday").textContent = `今日:认识 ${s.todayYes} · 不认识 ${s.todayNo}`;
  const judgedTotal = s.totalYes + s.totalNo;
  $("svAcc").textContent = judgedTotal
    ? `累计正确率 ${Math.round(s.accuracy * 100)}%(认识 ${fmt(s.totalYes)}/${fmt(judgedTotal)} 张)`
    : "累计正确率 –(还没判过)";
  renderChart(s.trend);
  $("statsView").hidden = false;
}

function closeStats() {
  statsOpen = false;
  $("statsView").hidden = true;
  render();
}

/* ---------- 词库总览 ---------- */
const LV_LABEL = { fresh: "未开始", learning: "学习中", done: "已毕业 ✓" };

function renderList() {
  const { counts, groups } = wordGroups(vocab.words, box.states);
  const pct = counts.total ? Math.round((counts.done / counts.total) * 100) : 0;
  $("lvProgress").textContent = `总数 ${fmt(counts.total)} · 已毕业 ${fmt(counts.done)}(${pct}%)`;
  $("lvBarFill").style.width = `${pct}%`;
  $("lvCounts").textContent = `学习中 ${fmt(counts.learning)} · 未开始 ${fmt(counts.fresh)}`;
  const q = listFilter.q.trim().toLowerCase();
  const frag = document.createDocumentFragment();
  for (const g of groups) {
    const items = g.items.filter((it) =>
      (listFilter.status === "all" || it.status === listFilter.status)
      && (!q || it.w.toLowerCase().includes(q)));
    if (!items.length) continue;
    const head = document.createElement("div");
    head.className = "lv-letter";
    head.textContent = g.letter;
    frag.append(head);
    for (const it of items) {
      const row = document.createElement("div");
      row.className = "lv-row";
      row.addEventListener("click", () => speak(it.w)); // 点行发音(词按钮聚焦回车同样冒泡触发)
      const idx = document.createElement("span");
      idx.className = "lv-idx";
      idx.textContent = it.idx;                    // 全表序号:搜索/筛选后不变
      const main = document.createElement("div");
      main.className = "lv-main";
      const wordBtn = document.createElement("button");
      wordBtn.type = "button";
      wordBtn.className = "lv-word";
      wordBtn.textContent = it.w;
      const def = document.createElement("div");
      def.className = "lv-def";
      def.textContent = it.def || "";              // 释义第二行,单行省略
      main.append(wordBtn, def);
      const tag = document.createElement("span");
      tag.className = `lv-tag ${it.status}`;
      tag.textContent = LV_LABEL[it.status];
      row.append(idx, main, tag);
      frag.append(row);
    }
  }
  if (!frag.childElementCount) {
    const empty = document.createElement("div");
    empty.className = "lv-empty";
    empty.textContent = "没有匹配的单词";
    frag.append(empty);
  }
  const listEl = $("lvList");
  listEl.textContent = "";
  listEl.append(frag);
}

function openList() {
  if (!vocab || !box) return;
  listOpen = true;
  hideCardArea();
  $("done").hidden = true;
  $("statsView").hidden = true; // 整卡画面互斥:统计开着时切到总览
  statsOpen = false;
  listFilter = { q: "", status: "all" }; // 每次打开都按当前进度重新拉取
  $("lvSearch").value = "";
  for (const c of $("lvChips").children) c.classList.toggle("on", c.dataset.f === "all");
  renderList();
  $("listView").hidden = false;
}

function closeList() {
  listOpen = false;
  $("listView").hidden = true;
  render();
}

/** 统计/总览都可能在开着(导入进度会改词池状态):一并复位再回卡片/完成画面。 */
function closeOverlays() {
  statsOpen = false;
  listOpen = false;
  $("statsView").hidden = true;
  $("listView").hidden = true;
  render();
}

/* ---------- 队列 ---------- */

function rebuildQueue() {
  const now = Date.now();
  const words = vocab.words.map((x) => x.w);
  const { queue: q, newToday } = buildQueue(words, box.states, now, settings.dailyLimit, box.meta);
  queue = q;
  judged = 0; reviewed = 0; fresh = 0;
  classified.clear();
  history = []; viewIndex = 0;
  // 当日新词发放数落库:同一天重复打开不会超额再发新词(保留 meta 既有字段,统计日志不清)
  box.meta = { ...box.meta, lastNewDate: new Date(now).toDateString(), lastNewCount: newToday };
  saveState(box);
}

/* ---------- 启动 ---------- */
async function init() {
  settings = loadSettings();
  $("dailyLimit").value = String(settings.dailyLimit);
  if (!canSpeak) document.body.classList.add("nospeak"); // 无语音合成则藏起 🔊

  let data;
  try {
    const res = await fetch("vocab.json");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    data = await res.json();
  } catch {
    showError();
    return;
  }
  if (!data || !Array.isArray(data.words)) { showError(); return; }

  vocab = data;
  vocabIndex = new Map(vocab.words.map((x) => [x.w, x]));
  box = loadState();
  if (!box.storageOk) $("warn").hidden = false; // 存不进去:顶部横幅提醒
  rebuildQueue();
  render();
}

/* ---------- 事件 ---------- */
$("speak").addEventListener("click", () => speak($("word").textContent));
$("btnNo").addEventListener("click", () => judge(false));
$("btnYes").addEventListener("click", () => judge(true));
$("prevBtn").addEventListener("click", lookBack);
$("nextBtn").addEventListener("click", returnNow);
$("chartBtn").addEventListener("click", openStats);
$("statsClose").addEventListener("click", closeStats);
$("doneStats").addEventListener("click", openStats);
$("listBtn").addEventListener("click", () => {
  $("panel").classList.remove("open");
  openList();
});
$("listClose").addEventListener("click", closeList);
$("lvSearch").addEventListener("input", () => {
  listFilter.q = $("lvSearch").value;
  renderList();
});
$("lvChips").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-f]");
  if (!b) return;
  listFilter.status = b.dataset.f;
  for (const c of $("lvChips").children) c.classList.toggle("on", c === b);
  renderList();
});
$("doneMore").addEventListener("click", () => {
  // 显式点击=用户意图,直接追加一批未发出的新词,不受「今日已发」扣减影响(那套上限只管自动发放);
  // 发放数照常记账,明日自动发放不会超发
  const now = Date.now();
  const batch = vocab.words.map((x) => x.w).filter((w) => !hasState(w)).slice(0, settings.dailyLimit);
  if (!batch.length) return;
  queue.push(...batch);
  const today = new Date(now).toDateString();
  if (box.meta.lastNewDate === today) box.meta.lastNewCount += batch.length;
  else { box.meta.lastNewDate = today; box.meta.lastNewCount = batch.length; }
  saveState(box);
  render();
});
$("retry").addEventListener("click", () => location.reload());

/* ⚙ 设置抽屉 */
$("gear").addEventListener("click", () => $("panel").classList.add("open"));
$("panelClose").addEventListener("click", () => $("panel").classList.remove("open"));

$("dailyLimit").addEventListener("change", () => {
  let n = Math.round(Number($("dailyLimit").value));
  if (!Number.isFinite(n) || n < 1) n = 1;
  $("dailyLimit").value = String(n);
  settings = { dailyLimit: n };
  saveSettings();
});

$("exportBtn").addEventListener("click", () => {
  if (!vocab || !box) return;
  const d = new Date();
  const stamp = `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, "0")}${String(d.getDate()).padStart(2, "0")}`;
  const payload = exportPayload(box, { version: vocab.version, generated_at: vocab.generated_at });
  const url = URL.createObjectURL(new Blob([payload], { type: "application/json" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = `vocab-backup-${stamp}.json`;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
});

$("resetBtn").addEventListener("click", () => {
  const ok = window.confirm(
    "确定重置吗?\n\n全部复习状态与统计将被清空(词池不受影响),从第一天重新开始。\n建议先「导出进度」留一份备份。");
  if (!ok) return;
  try { localStorage.removeItem(STORAGE_KEY); } catch { /* 隐私模式 */ }
  location.reload();
});

$("importFile").addEventListener("change", () => {
  const input = $("importFile");
  if (!vocab || !box) { input.value = ""; return; }
  const file = input.files && input.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => {
    try {
      box = mergeImport(box, JSON.parse(String(reader.result)));
    } catch {
      toast("导入文件格式不对"); // 解析/校验失败:保持当前状态不动
      input.value = "";
      return;
    }
    saveState(box);
    rebuildQueue();
    closeOverlays(); // 统计/总览可能开着:一并关掉再回到卡片/完成画面
    $("panel").classList.remove("open");
    toast("已导入");
    input.value = ""; // 允许再次选同一文件
  };
  reader.onerror = () => { toast("导入文件格式不对"); input.value = ""; };
  reader.readAsText(file);
});

/* 键盘:← 不认识,→ 认识;回看时 ←/→ 翻看;Esc 关统计/总览;输入框/设置面板聚焦或打开时忽略 */
document.addEventListener("keydown", (e) => {
  const t = e.target;
  if (t && t.closest && t.closest("input, textarea, select, #panel")) return;
  if ($("panel").classList.contains("open")) return;
  if (statsOpen) {
    if (e.key === "Escape") closeStats();
    return;
  }
  if (listOpen) {
    if (e.key === "Escape") closeList();
    return;
  }
  if (!vocab || !queue.length) return;
  if (viewIndex > 0) { // 回看模式:方向键只在历史与当前之间移动,不判定
    if (e.key === "ArrowLeft") { e.preventDefault(); lookBack(); }
    else if (e.key === "ArrowRight") { e.preventDefault(); returnNow(); }
    return;
  }
  if (e.key === "ArrowLeft") {
    e.preventDefault();
    judge(false);
  } else if (e.key === "ArrowRight") {
    e.preventDefault();
    judge(true);
  }
});

init();
