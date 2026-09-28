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
