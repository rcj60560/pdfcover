// subtitle-viewer/app.js —— 副作用层：fetch / DOM / 计时 / 滚动。逻辑全在 core.js。
import {
  esc, parseSubtitleMd, currentBlockIndex, isEnded, SyncClock, formatMs,
  renderBlock, groupManifest, plainText, renderPlain, targetScrollTop,
} from "./core.js?v=7";

const $ = (sel) => document.querySelector(sel);

const state = {
  clock: new SyncClock(),
  blocks: [],
  keyframes: [],      // [{t, y}] 每块居中 scrollTop，连续滚动插值用
  follow: true,
  ended: false,
  activeIdx: -1,
  timer: null,
  rafId: null,
  wakeLock: null,
};

/* ---------- 列表视图 ---------- */

async function loadManifest() {
  let manifest = { docs: [] };
  try {
    const res = await fetch("manifest.json", { cache: "no-store" });   // 列表必须拿最新（浏览器启发式缓存会赖着旧 manifest）
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
  state.plain = plainText(state.blocks);
  $("#doc").insertAdjacentHTML("beforeend", renderPlain(state.plain));
  $("#plain-jump").hidden = false;
  measureKeyframes();
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
  state.rafId = requestAnimationFrame(followFrame);
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
  if (idx !== state.activeIdx) setActive(idx);       // 滚动交给 rAF 循环
}

function setActive(idx) {
  const prev = document.querySelector(".blk.is-on");
  if (prev) prev.classList.remove("is-on");
  state.activeIdx = idx;
  const el = document.querySelector(`.blk[data-i="${idx}"]`);
  if (el) el.classList.add("is-on");
}

/* ---------- 连续跟随滚动：时间插值 + 指数平滑，换句不跳 ---------- */

function measureKeyframes() {          // 每块的居中 scrollTop（resize 后重算）
  const vh = window.innerHeight;
  state.keyframes = state.blocks
    .map((b, i) => {
      const el = document.querySelector(`.blk[data-i="${i}"]`);
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return { t: b.startMs, y: r.top + window.scrollY + r.height / 2 - vh / 2 };
    })
    .filter(Boolean);
}

function followFrame() {
  state.rafId = requestAnimationFrame(followFrame);
  if (!state.follow || !state.keyframes.length) return;
  const target = targetScrollTop(state.clock.elapsedMs, state.keyframes);
  if (target == null) return;
  window.scrollTo(0, window.scrollY + (target - window.scrollY) * 0.1);
}

window.addEventListener("resize", () => { if (state.timer) measureKeyframes(); });

/* ---------- 交互 ---------- */

$("#back").addEventListener("click", () => { location.href = location.pathname; });

$("#minus5").addEventListener("click", () => state.clock.shift(-5000));
$("#minus1").addEventListener("click", () => state.clock.shift(-1000));
$("#plus1").addEventListener("click", () => state.clock.shift(1000));
$("#plus5").addEventListener("click", () => state.clock.shift(5000));

$("#plain-jump").addEventListener("click", () => {
  document.querySelector("#plain")
    ?.scrollIntoView({ behavior: "smooth", block: "start" });
});

async function copyText(text) {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch { /* http 非安全上下文无此 API 或被拒 → 降级 execCommand */ }
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.style.cssText = "position:fixed;opacity:0";
  document.body.appendChild(ta);
  ta.select();
  let ok = false;
  try { ok = document.execCommand("copy"); } catch { ok = false; }
  ta.remove();
  return ok;
}

$("#doc").addEventListener("click", async (e) => {        // 复制英文/中文（委托：#plain 是动态插入的）
  const btn = e.target.closest(".copy-btn");
  if (!btn) return;
  const text = state.plain?.[btn.dataset.copy] || "";
  btn.disabled = true;
  btn.textContent = (await copyText(text)) ? "✓ 已复制" : "✗ 失败";
  setTimeout(() => { btn.disabled = false; btn.textContent = "📋 复制"; }, 1500);
});

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
});

$("#back-cur").addEventListener("click", () => {
  state.follow = true;
  $("#back-cur").hidden = true;
});

/* 用户手指拖动/滚轮 → 暂停跟随（rAF 的 window.scrollTo 不触发这两个事件） */
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
