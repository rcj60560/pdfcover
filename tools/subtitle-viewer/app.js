// subtitle-viewer/app.js —— 副作用层：fetch / DOM / 计时 / 滚动。逻辑全在 core.js。
import {
  esc, parseSubtitleMd, currentBlockIndex, isEnded, SyncClock, formatMs,
  renderBlock, groupManifest,
} from "./core.js";

const $ = (sel) => document.querySelector(sel);

const state = {
  clock: new SyncClock(),
  blocks: [],
  follow: true,
  ended: false,
  activeIdx: -1,
  timer: null,
  wakeLock: null,
};

/* ---------- 列表视图 ---------- */

async function loadManifest() {
  let manifest = { docs: [] };
  try {
    const res = await fetch("manifest.json");
    if (res.ok) manifest = await res.json();
  } catch { /* 网络失败 → 空列表提示 */ }
  renderList(manifest.docs || []);
}

function renderList(docs) {
  if (!docs.length) {
    $("#list").innerHTML =
      `<p class="empty">还没有字幕。先在电脑上跑 <code>python sync_subtitles.py</code> 上传。</p>`;
    return;
  }
  $("#list").innerHTML = groupManifest(docs).map((g) =>
    `<h2 class="group">${esc(g.dir)}</h2><ul class="docs">` +
    g.items.map((d) =>
      `<li><a class="doc" href="?doc=${encodeURIComponent(d.path)}">` +
      `<span class="doc-title">${esc(d.title)}</span>` +
      `<span class="doc-meta">${d.count} 条 · ${formatMs(d.duration * 1000)}</span>` +
      `</a></li>`).join("") +
    `</ul>`).join("");
}

/* ---------- 字幕视图 ---------- */

async function openDoc(rel) {
  let text;
  try {
    const url = "docs/" + rel.split("/").map(encodeURIComponent).join("/");
    const res = await fetch(url);
    if (!res.ok) throw new Error(res.status);
    text = await res.text();
  } catch {
    alert("字幕加载失败，请重试");
    location.href = location.pathname;
    return;
  }
  $("#doc-title").textContent = rel.split("/").pop().replace(/\.md$/i, "");
  const parsed = parseSubtitleMd(text);
  state.blocks = parsed.blocks;

  if (!parsed.hasTimestamps) return enterStaticMode(text);
  $("#blocks").innerHTML = state.blocks.map((b, i) => renderBlock(b, i, false)).join("");
  enterStandby();
}

function enterStaticMode(text) {
  $("#controls").hidden = true;
  $("#clock").hidden = true;
  $("#blocks").classList.add("static");
  $("#blocks").innerHTML = text.replace(/\r\n/g, "\n").split(/\n-{3,}\n/)
    .map((c) => c.trim()).filter(Boolean)
    .map((c) => `<section class="blk"><p class="en">${esc(c)}</p></section>`).join("");
}

function enterStandby() {
  $("#standby").hidden = false;
  $("#standby-btn").addEventListener("click", startFollowing, { once: true });
}

function startFollowing() {
  $("#standby").hidden = true;
  $("#controls").hidden = false;
  state.clock.start(0);
  state.timer = setInterval(tick, 500);
  tick();
  keepAwake(true);
}

function tick() {
  const ms = state.clock.elapsedMs;
  $("#clock").textContent = formatMs(ms);
  if (isEnded(state.blocks, ms)) {
    if (!state.ended) { state.ended = true; $("#ended").hidden = false; }
    return;
  }
  state.ended = false;
  $("#ended").hidden = true;
  const idx = currentBlockIndex(state.blocks, ms);
  if (idx !== state.activeIdx) {
    setActive(idx);
    if (state.follow) scrollToActive();
  }
}

function setActive(idx) {
  const prev = document.querySelector(".blk.is-on");
  if (prev) prev.classList.remove("is-on");
  state.activeIdx = idx;
  const el = document.querySelector(`.blk[data-i="${idx}"]`);
  if (el) el.classList.add("is-on");
}

function scrollToActive() {
  document.querySelector(`.blk[data-i="${state.activeIdx}"]`)
    ?.scrollIntoView({ behavior: "smooth", block: "center" });
}

/* ---------- 交互 ---------- */

$("#back").addEventListener("click", () => { location.href = location.pathname; });

$("#minus5").addEventListener("click", () => state.clock.shift(-5000));
$("#plus5").addEventListener("click", () => state.clock.shift(5000));

$("#playpause").addEventListener("click", () => {
  if (state.clock.paused) { state.clock.resume(); $("#playpause").textContent = "⏸"; }
  else { state.clock.pause(); $("#playpause").textContent = "▶"; }
});

$("#blocks").addEventListener("click", (e) => {           // 点时间戳 → 锚定
  const btn = e.target.closest(".ts");
  if (!btn || !state.timer) return;
  const i = Number(btn.dataset.i);
  state.clock.anchorTo(state.blocks[i].startMs);
  state.follow = true;
  $("#back-cur").hidden = true;
  setActive(i);
  scrollToActive();
});

$("#back-cur").addEventListener("click", () => {
  state.follow = true;
  $("#back-cur").hidden = true;
  scrollToActive();
});

/* 用户手指拖动/滚轮 → 暂停跟随（scrollIntoView 不触发这两个事件） */
for (const ev of ["touchmove", "wheel"]) {
  document.addEventListener(ev, () => {
    if (state.timer && state.follow && !state.ended) {
      state.follow = false;
      $("#back-cur").hidden = false;
    }
  }, { passive: true });
}

/* ---------- 屏幕常亮（失败静默降级） ---------- */

async function keepAwake(on) {
  try {
    if (on && "wakeLock" in navigator) {
      state.wakeLock = await navigator.wakeLock.request("screen");
    } else {
      await state.wakeLock?.release();
      state.wakeLock = null;
    }
  } catch { state.wakeLock = null; }
}
document.addEventListener("visibilitychange", () => {
  if (state.timer) keepAwake(!document.hidden);
});

/* ---------- 路由 ---------- */

const doc = new URLSearchParams(location.search).get("doc");
if (doc) {
  $("#list").hidden = true;
  $("#doc").hidden = false;
  $("#back").hidden = false;
  $("#app-title").hidden = true;
  $("#doc-title").hidden = false;
  $("#clock").hidden = false;
  openDoc(doc);
} else {
  loadManifest();
}
