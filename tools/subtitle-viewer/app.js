// subtitle-viewer/app.js —— 副作用层：fetch / DOM / 计时 / 滚动。逻辑全在 core.js。
import {
  esc, parseSubtitleMd, currentBlockIndex, isEnded, SyncClock, formatMs,
  renderBlock, groupBooks, groupUnits, plainText, renderPlain, targetScrollTop,
} from "./core.js?v=10";

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
  const docs = manifest.docs || [];
  const params = new URLSearchParams(location.search);
  const book = params.get("book");
  const unit = params.get("unit");
  if (book && unit) renderRecordings(docs, book, unit);
  else if (book) renderUnits(docs, book);
  else renderBooks(docs);
}

function gridCard(href, title, meta) {
  return `<a class="card" href="${href}">` +
    `<span class="card-title">${esc(title)}</span>` +
    `<span class="card-meta">${meta}</span></a>`;
}

function renderBooks(docs) {
  const books = groupBooks(docs);
  $("#app-title").textContent = "字幕跟读器";
  if (!books.length) {
    $("#list").innerHTML =
      `<p class="empty">还没有字幕。先在电脑上跑 <code>python sync_subtitles.py</code> 上传。</p>`;
    return;
  }
  $("#list").innerHTML = `<div class="grid">` + books.map((b) =>
    gridCard(location.pathname + "?book=" + encodeURIComponent(b.dir),
      b.dir, `${b.docs} 篇 · ${formatMs(b.duration * 1000)}`)).join("") + `</div>`;
}

function renderUnits(docs, book) {
  const items = docs.filter((d) =>
    d.path.startsWith(book + "/") ||
    (book === "其他" && !d.path.includes("/")));
  $("#app-title").textContent = items.length ? book : "没有这本书";
  $("#back").hidden = false;
  $("#back").textContent = "‹ 书库";
  if (!items.length) {
    $("#list").innerHTML = `<p class="empty">这本书还没有字幕。</p>`;
    return;
  }
  const { units, flat } = groupUnits(items);
  const cards = [
    ...units.map((u) =>
      gridCard(location.pathname + (u.doc
        ? "?doc=" + encodeURIComponent(u.doc)                   // 单篇 Unit:直达文档
        : "?book=" + encodeURIComponent(book) + "&unit=" + encodeURIComponent(u.dir)),
        u.dir, `${u.count} 条 · ${formatMs(u.duration * 1000)}`)),
    ...flat.map((d) =>
      gridCard(location.pathname + "?doc=" + encodeURIComponent(d.path),
        d.title, `${d.count} 条 · ${formatMs(d.duration * 1000)}`)),
  ];
  $("#list").innerHTML = `<div class="grid list">` + cards.join("") + `</div>`;
}

function renderRecordings(docs, book, unit) {          // 三级:Unit → Recording 网格
  const prefix = (book === "其他" ? "" : book + "/") + unit + "/";
  const items = docs.filter((d) => d.path.startsWith(prefix));
  $("#app-title").textContent = unit;
  $("#back").hidden = false;
  $("#back").textContent = "‹ " + book;
  $("#list").innerHTML = items.length
    ? `<div class="grid list">` + items.map((d) =>
        gridCard(location.pathname + "?doc=" + encodeURIComponent(d.path),
          d.title, `${d.count} 条 · ${formatMs(d.duration * 1000)}`)).join("") + `</div>`
    : `<p class="empty">这个 Unit 还没有字幕。</p>`;
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

$("#back").addEventListener("click", () => {          // 三级路由感知返回
  const p = new URLSearchParams(location.search);
  if (p.get("unit")) {
    location.href = location.pathname + "?book=" + encodeURIComponent(p.get("book") || "");
  } else {
    location.href = location.pathname;
  }
});

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
