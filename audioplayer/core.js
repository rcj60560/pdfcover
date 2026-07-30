// audioplayer/core.js
// 纯逻辑 + 渲染辅助，无副作用（无 DOM / 网络 / <audio>），可在 node:test 中单测。

export const LOOP_MODES = ["off", "one", "all"];
export const SPEEDS = [0.75, 1, 1.25, 1.5];
const CARD_COLORS = [
  "#e57373", "#f06292", "#ba68c8", "#7986cb", "#4fc3f7",
  "#4db6ac", "#81c784", "#ffb74d", "#a1887f", "#90a4ae",
];

export function parseBooks(entries) {
  if (!Array.isArray(entries)) return [];
  return entries
    .filter((e) => e && e.type === "directory")
    .map((e) => e.name)
    .sort((a, b) => {
      const aNumber = Number(String(a).match(/\d+/)?.[0]);
      const bNumber = Number(String(b).match(/\d+/)?.[0]);
      if (Number.isFinite(aNumber) && Number.isFinite(bNumber) && aNumber !== bNumber) {
        return aNumber - bNumber;
      }
      return String(a).localeCompare(String(b), "zh-CN");
    });
}

export function parseTracks(entries) {
  if (!Array.isArray(entries)) return [];
  return entries
    .filter((e) => e && e.type === "file" && /\.mp3$/i.test(e.name))
    .map((e) => e.name);
}

export function sortTracks(names) {
  return [...names].sort((a, b) => {
    const na = parseInt(a, 10);
    const nb = parseInt(b, 10);
    if (!isNaN(na) && !isNaN(nb)) {
      if (na !== nb) return na - nb;
      return a.localeCompare(b);
    }
    if (!isNaN(na)) return -1;
    if (!isNaN(nb)) return 1;
    return a.localeCompare(b);
  });
}

export function cycleLoop(mode) {
  const i = LOOP_MODES.indexOf(mode);
  return LOOP_MODES[(i + 1) % LOOP_MODES.length];
}

export function cycleSpeed(speed) {
  const i = SPEEDS.indexOf(speed);
  return i === -1 ? 1 : SPEEDS[(i + 1) % SPEEDS.length];
}

export function nextTrack(index, total, loopMode) {
  if (loopMode === "one") return index;
  if (index < total - 1) return index + 1;
  if (loopMode === "all") return 0;
  return null;
}

export function clampSeek(time, duration) {
  if (!Number.isFinite(duration) || duration <= 0) return 0;
  return Math.max(0, Math.min(time, duration));
}

export function formatTime(sec) {
  if (!Number.isFinite(sec) || sec < 0) sec = 0;
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

function esc(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function colorFor(name) {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0;
  return CARD_COLORS[h % CARD_COLORS.length];
}

export function renderBookCard(name, count) {
  const first = String(name).match(/\d+/)?.[0] || [...String(name)][0] || "?";
  const color = colorFor(String(name));
  const countLabel = Number.isFinite(count) ? `${count}集` : "";
  return (
    `<button class="card" data-book="${esc(name)}" style="--card-color:${color}">` +
    `<span class="card-cover" style="background:${color}">${esc(first)}</span>` +
    `<span class="card-title">${esc(name)}</span>` +
    `<span class="card-count">${countLabel}</span>` +
    `</button>`
  );
}

export function renderTrackRow(name, index, isCurrent) {
  const normalized = String(name).match(/^T(\d+)(?:-P(\d+))?\.mp3$/i);
  const fallback = String(name).match(/(\d+)/);
  const label = normalized
    ? `Test ${Number(normalized[1])}${normalized[2] ? ` · Part ${Number(normalized[2])}` : ""}`
    : fallback ? fallback[1] : name;
  return (
    `<li class="track${isCurrent ? " is-current" : ""}" data-file="${esc(name)}" data-index="${index}" title="${esc(name)}">` +
    `<span class="track-num">${esc(label)}</span>` +
    `</li>`
  );
}
