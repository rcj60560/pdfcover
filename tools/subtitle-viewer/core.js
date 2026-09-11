// subtitle-viewer/core.js
// 纯逻辑 + 渲染辅助，无副作用（无 DOM / 网络），node:test 单测。

export function esc(s) {
  return String(s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

const TS_RE = /^`(\d{1,2}:\d{2}(?::\d{2})?)\s*→\s*(\d{1,2}:\d{2}(?::\d{2})?)`$/;

export function parseTs(s) {
  const p = s.split(":").map(Number);
  return p.length === 3
    ? ((p[0] * 60 + p[1]) * 60 + p[2]) * 1000
    : (p[0] * 60 + p[1]) * 1000;
}

export function parseSubtitleMd(text) {
  const blocks = [];
  const chunks = String(text).replace(/\r\n/g, "\n").split(/\n-{3,}\n/);
  for (const chunk of chunks) {
    const lines = chunk.split("\n").map((l) => l.trim()).filter(Boolean);
    const tsLine = lines.find((l) => TS_RE.test(l));
    if (!tsLine) continue;                          // 头部/无时间戳块：跳过
    const m = tsLine.match(TS_RE);
    const en = lines
      .filter((l) => /^\*\*.+\*\*$/.test(l))
      .map((l) => l.replace(/^\*\*/, "").replace(/\*\*$/, ""))
      .join(" ");
    const zh = lines
      .filter((l) => l !== tsLine && !/^\*\*.+\*\*$/.test(l))
      .join("\n");
    blocks.push({
      startMs: parseTs(m[1]), endMs: parseTs(m[2]), en, zh,
      tsLabel: m[0].slice(1, -1),
    });
  }
  return { blocks, hasTimestamps: blocks.length > 0 };
}

export function currentBlockIndex(blocks, ms) {
  let ans = -1;
  for (let i = 0; i < blocks.length; i++) {
    if (blocks[i].startMs <= ms) ans = i; else break;
  }
  return ans;
}

export function isEnded(blocks, ms) {
  return blocks.length > 0 && ms >= blocks[blocks.length - 1].endMs;
}

export class SyncClock {
  constructor(now = () => performance.now()) {
    this._now = now;
    this._t0 = null;        // 启动参考点
    this._offsetMs = 0;     // 锚定初值 + ±5s 累计
    this._pausedTotal = 0;  // 累计暂停时长
    this._pausedAt = null;
  }
  get paused() { return this._pausedAt !== null; }
  start(atMs = 0) {
    this._t0 = this._now();
    this._offsetMs = atMs;
    this._pausedTotal = 0;
    this._pausedAt = null;
  }
  get elapsedMs() {
    if (this._t0 === null) return 0;
    const ref = this._pausedAt ?? this._now();
    return Math.max(0, this._offsetMs + (ref - this._t0) - this._pausedTotal);
  }
  shift(deltaMs) { this._offsetMs += deltaMs; }
  anchorTo(targetMs) {   // 让 elapsed 立即等于 targetMs（重置参考点）
    this._t0 = this._now();
    this._offsetMs = targetMs;
    this._pausedTotal = 0;
    if (this._pausedAt !== null) this._pausedAt = this._now();
  }
  pause() { if (this._t0 !== null && !this.paused) this._pausedAt = this._now(); }
  resume() {
    if (this.paused) {
      this._pausedTotal += this._now() - this._pausedAt;
      this._pausedAt = null;
    }
  }
}

export function formatMs(ms) {
  if (!Number.isFinite(ms) || ms < 0) ms = 0;
  const t = Math.floor(ms / 1000);
  const h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), s = t % 60;
  return h > 0
    ? `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`
    : `${m}:${String(s).padStart(2, "0")}`;
}

export function renderBlock(b, i, active) {
  return (
    `<section class="blk${active ? " is-on" : ""}" data-i="${i}">` +
    `<button class="ts" data-i="${i}">${esc(b.tsLabel)}</button>` +
    `<p class="en">${esc(b.en)}</p>` +
    (b.zh ? `<p class="zh">${esc(b.zh)}</p>` : "") +
    `</section>`
  );
}

export function groupManifest(docs) {
  const map = new Map();
  for (const d of docs) {
    const dir = d.path.includes("/") ? d.path.slice(0, d.path.lastIndexOf("/")) : "";
    if (!map.has(dir)) map.set(dir, []);
    map.get(dir).push(d);
  }
  return [...map.entries()]
    .sort((a, b) => a[0].localeCompare(b[0], "zh-CN"))
    .map(([dir, items]) => ({ dir: dir || "字幕", items }));
}
