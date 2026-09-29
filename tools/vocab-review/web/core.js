/** vocab-review 纯逻辑:SM-2 简化版 + 每日队列。状态:{e,i,r,due,g},词键=词形原形。 */
const DAY = 86400000;

export function newState() { return { e: 2.5, i: 0, r: 0, due: 0, g: false }; }

export function answerYes(state, now) {
  const r = state.r + 1;
  const i = r === 1 ? 1 : r === 2 ? 3 : Math.round(state.i * state.e);
  return { e: state.e, i, r, due: now + i * DAY, g: r >= 4 || i >= 21 };
}

export function answerNo(state, now) {
  return { e: Math.max(1.3, state.e - 0.2), i: 0, r: 0, due: now + 600000, g: false };
}

export function endOfToday(now) {
  const d = new Date(now);
  d.setHours(23, 59, 59, 999);
  return d.getTime();
}

export function buildQueue(words, states, now, dailyLimit, meta) {
  const today = new Date(now).toDateString();
  const used = meta.lastNewDate === today ? meta.lastNewCount : 0;
  const review = [], fresh = [];
  for (const w of words) {
    const s = states[w];
    if (s && !s.g) { if (s.due <= endOfToday(now)) review.push([s.due, w]); }
    else if (!s) fresh.push(w);
  }
  review.sort((a, b) => a[0] - b[0]);
  const newWords = fresh.slice(0, Math.max(0, dailyLimit - used));
  return { queue: [...review.map((x) => x[1]), ...newWords], newToday: used + newWords.length };
}

export const STORAGE_KEY = "vocab-review-state-v1";

/* ---------- 词库总览 ---------- */

const byAlpha = (a, b) => (a < b ? -1 : a > b ? 1 : 0);

/** 词库总览分组:按首字母分节 + 每词三态标注(fresh/learning/done)。
 *  words = 词表(vocab.words.map(x=>x.w)),states = 进度盒 states。
 *  非 a-z 开头的词归入 "#" 节,排在字母节之后;节内按字母序,无词的字母不出现。 */
export function wordGroups(words, states) {
  const st = states || {};
  const counts = { total: words.length, done: 0, learning: 0, fresh: 0 };
  const byLetter = new Map();
  for (const w of words) {
    const s = st[w];
    const status = s ? (s.g ? "done" : "learning") : "fresh";
    counts[status] += 1;
    const first = w.charAt(0);
    const letter = /[a-z]/i.test(first) ? first.toUpperCase() : "#";
    if (!byLetter.has(letter)) byLetter.set(letter, []);
    byLetter.get(letter).push({ w, status });
  }
  const groups = [...byLetter.entries()]
    .map(([letter, items]) => ({ letter, items: items.sort((x, y) => byAlpha(x.w, y.w)) }))
    .sort((x, y) => (x.letter === "#" ? 1 : y.letter === "#" ? -1 : byAlpha(x.letter, y.letter)));
  return { counts, groups };
}

/* ---------- 统计 ---------- */

function dayKey(now) {
  const d = new Date(now);
  const pad = (x) => String(x).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** 每次判定后记账:返回更新后的 meta(新对象,不改入参)。
 *  meta.dailyLog = { "YYYY-MM-DD": {y: n, n: n} },totalYes/totalNo 为累计判定数。
 *  旧存档缺这些字段时可兼容:按零处理。 */
export function logJudge(meta, now, isYes) {
  const base = meta || {};
  const key = dayKey(now);
  const log = { ...(base.dailyLog || {}) };
  const day = { y: 0, n: 0, ...log[key] };
  log[key] = { y: day.y + (isYes ? 1 : 0), n: day.n + (isYes ? 0 : 1) };
  return {
    ...base,
    dailyLog: log,
    totalYes: (base.totalYes || 0) + (isYes ? 1 : 0),
    totalNo: (base.totalNo || 0) + (isYes ? 0 : 1),
  };
}

/** 汇总统计视图模型:词池四态 + 今日判定 + 累计正确率 + 近 7 日趋势。
 *  words=当前词池的词表,states=进度盒 states,vocabStats=vocab.json 的 stats。 */
export function summarize(words, states, meta, vocabStats, now = Date.now()) {
  const m = meta || {};
  const st = states || {};
  let graduated = 0, learning = 0, notStarted = 0;
  for (const w of words) {
    const s = st[w];
    if (s && s.g) graduated += 1;
    else if (s) learning += 1;      // 有状态 = 见过(判定过至少一次)
    else notStarted += 1;
  }
  const total = (vocabStats && (vocabStats.candidate + vocabStats.known)) || words.length;
  const today = m.dailyLog && m.dailyLog[dayKey(now)];
  const totalYes = m.totalYes || 0, totalNo = m.totalNo || 0;
  const trend = [];
  for (let i = 6; i >= 0; i--) {
    const key = dayKey(now - i * DAY);
    const day = (m.dailyLog && m.dailyLog[key]) || { y: 0, n: 0 };
    trend.push({ key, y: day.y || 0, n: day.n || 0 });
  }
  return {
    total, graduated, learning, notStarted,
    todayYes: (today && today.y) || 0,
    todayNo: (today && today.n) || 0,
    totalYes, totalNo,
    accuracy: totalYes + totalNo ? totalYes / (totalYes + totalNo) : 0,
    trend,
  };
}

export function emptyBox() {
  return { states: {}, meta: { lastNewDate: "", lastNewCount: 0 } };
}

export function mergeImport(current, imported) {
  if (!imported || typeof imported !== "object"
    || typeof imported.states !== "object" || imported.states === null
    || typeof imported.meta !== "object") {
    throw new Error("导入文件格式不对");
  }
  return { states: { ...imported.states }, meta: { ...imported.meta } };
}

export function loadState() {
  const box = emptyBox();
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) Object.assign(box, JSON.parse(raw));
    box.storageOk = true;
  } catch { box.storageOk = false; }
  return box;
}

export function saveState(box) {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(box)); } catch { /* 隐私模式 */ }
}

export function exportPayload(box, vocabMeta) {
  return JSON.stringify({ exportedAt: new Date().toISOString(), vocab: vocabMeta, ...box }, null, 1);
}
