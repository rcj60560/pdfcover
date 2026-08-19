// speaking-player/core.js
// 纯逻辑 + 渲染辅助，无副作用（无 DOM / 网络 / <audio>），node:test 单测。

function esc(s) {
  return String(s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

export function parseTracks(entries) {
  if (!Array.isArray(entries)) return [];
  const names = new Set(entries.filter((e) => e && e.type === "file").map((e) => e.name));
  return entries
    .filter((e) => e && e.type === "file" && /\.mp3$/i.test(e.name))
    .map((e) => ({
      file: e.name,
      name: e.name.replace(/\.mp3$/i, ""),
      hasSubtitle: names.has(e.name.replace(/\.mp3$/i, "") + ".json"),
    }));
}

export function sortTracks(tracks) {
  return [...tracks].sort((a, b) => a.file.localeCompare(b.file, "zh-CN",
    { numeric: true, sensitivity: "base" }));
}

export function currentWordIndex(words, tMs) {
  let lo = 0, hi = words.length - 1, ans = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (words[mid].s <= tMs) { ans = mid; lo = mid + 1; } else hi = mid - 1;
  }
  return ans;
}

export function currentSentenceIndex(sentences, tMs) {
  let lo = 0, hi = sentences.length - 1, ans = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (sentences[mid].start <= tMs) { ans = mid; lo = mid + 1; } else hi = mid - 1;
  }
  return ans;
}

export function sentenceRange(sentences, idx) {
  if (!Array.isArray(sentences) || idx < 0 || idx >= sentences.length) return null;
  return { start: sentences[idx].start, end: sentences[idx].end };
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

export function renderTrackRow(track, index, isCurrent) {
  const sub = track.hasSubtitle ? "" : `<span class="no-sub">无字幕</span>`;
  return (
    `<li class="track${isCurrent ? " is-current" : ""}" data-index="${index}" title="${esc(track.file)}">` +
    `<span class="track-name">${esc(track.name)}</span>${sub}</li>`
  );
}

export function renderSentence(words, i, j, activeIdx) {
  let html = "";
  for (let k = i; k <= j; k++) {
    const cls = k < activeIdx ? "w-done" : k === activeIdx ? "w-on" : "";
    html += `<span class="w ${cls}" data-w="${k}">${esc(words[k].t)}</span> `;
  }
  return html;
}
