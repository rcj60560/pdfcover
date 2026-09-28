/** vocab-review 复习页:加载词库 → 建队列 → 卡片流(翻面/判定/发音)+ 设置抽屉(每日上限/导出/导入)。纯逻辑在 core.js。 */
import {
  newState, answerYes, answerNo, buildQueue,
  mergeImport, loadState, saveState, exportPayload,
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
let revealed = false;        // 当前卡是否已翻面
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
  revealed = false;
  const w = queue[0];
  const item = vocabIndex.get(w) || { phon: "", def: "", tags: "", sents: [] };
  $("src").textContent = hasState(w) ? "复习 · 到期重现" : "生词候选 · 来自词池";
  $("word").textContent = w;
  $("phon").textContent = item.phon || "";
  $("faceFront").hidden = false;
  $("faceBack").hidden = true;
  $("flash").hidden = false;
  $("judge").hidden = false;
  $("judge").classList.remove("show");
  $("hint").hidden = true;
}

function renderBack() {
  const w = queue[0];
  const item = vocabIndex.get(w) || { phon: "", def: "", tags: "", sents: [] };
  $("wordBack").textContent = w;
  $("phonBack").textContent = [item.phon, item.tags].filter(Boolean).join(" · ");
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
}

/* ---------- 卡片流 ---------- */
function reveal() {
  if (revealed || !queue.length) return;
  revealed = true;
  renderBack();
  $("faceFront").hidden = true;
  $("faceBack").hidden = false;
  $("judge").classList.add("show");
  $("hint").hidden = false;
}

function judge(yes) {
  if (!revealed || !queue.length) return;
  const w = queue.shift(); // 当前卡出队
  const now = Date.now();
  if (!classified.has(w)) { classified.add(w); hasState(w) ? reviewed++ : fresh++; }
  const next = (yes ? answerYes : answerNo)(box.states[w] || newState(), now);
  box.states[w] = next;
  saveState(box); // 判定即落盘
  if (next.g) toast(`🎓 ${w} 毕业!`); // 队列里的词必非毕业态,next.g 即刚毕业
  if (!yes) queue.splice(Math.min(10, queue.length), 0, w); // 隔 10 张重现,至多插到队尾
  judged++;
  render();
}

function render() {
  renderStats();
  renderProgress();
  $("done").hidden = true;
  $("error").hidden = true;
  if (!queue.length) { showDone(); return; }
  renderCard();
}

function hideCardArea() {
  $("flash").hidden = true;
  $("judge").hidden = true;
  $("judge").classList.remove("show");
  $("hint").hidden = true;
}

function showDone() {
  hideCardArea();
  $("doneCount").textContent = `复习 ${reviewed} · 新词 ${fresh}`;
  $("done").hidden = false;
}

function showError() {
  hideCardArea();
  $("error").hidden = false;
}

/* ---------- 队列 ---------- */
function rebuildQueue() {
  const now = Date.now();
  const words = vocab.words.map((x) => x.w);
  const { queue: q, newToday } = buildQueue(words, box.states, now, settings.dailyLimit, box.meta);
  queue = q;
  judged = 0; reviewed = 0; fresh = 0;
  classified.clear();
  // 当日新词发放数落库:同一天重复打开不会超额再发新词
  box.meta = { lastNewDate: new Date(now).toDateString(), lastNewCount: newToday };
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
$("speakBack").addEventListener("click", () => speak($("wordBack").textContent));
$("reveal").addEventListener("click", reveal);
$("btnNo").addEventListener("click", () => judge(false));
$("btnYes").addEventListener("click", () => judge(true));
$("refresh").addEventListener("click", () => location.reload());
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
    render();
    $("panel").classList.remove("open");
    toast("已导入");
    input.value = ""; // 允许再次选同一文件
  };
  reader.onerror = () => { toast("导入文件格式不对"); input.value = ""; };
  reader.readAsText(file);
});

/* 键盘:空格翻面,← 不认识,→ 认识;输入框/设置面板聚焦或打开时忽略 */
document.addEventListener("keydown", (e) => {
  const t = e.target;
  if (t && t.closest && t.closest("input, textarea, select, #panel")) return;
  if ($("panel").classList.contains("open")) return;
  if (!vocab || !queue.length) return;
  if (e.key === " " || e.code === "Space") {
    e.preventDefault();
    reveal();
  } else if (e.key === "ArrowLeft") {
    if (revealed) { e.preventDefault(); judge(false); }
  } else if (e.key === "ArrowRight") {
    if (revealed) { e.preventDefault(); judge(true); }
  }
});

init();
