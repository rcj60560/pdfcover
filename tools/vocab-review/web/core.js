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
