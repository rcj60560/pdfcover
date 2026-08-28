// ielts-topics/app.js — DOM 装配：取数、hash 路由、桌面侧边栏（单一展开手风琴）+
// 移动端层级视图、翻译显示切换（逐句/整段）。纯逻辑在 core.js（node:test 覆盖）。
import { esc, parseHash, findUnit, findTopic, sampleHtml, sideHtml } from "./core.js";

const app = document.getElementById("app");
const side = document.getElementById("side");
const foot = document.getElementById("foot");
const wide = matchMedia("(min-width: 960px)");

let DATA = null;
let openUnit = null;                                       // 侧边栏唯一展开的单元
let trMode = localStorage.getItem("trMode") || "sent";     // 翻译显示：sent 逐句 | para 整段

/* ---------- 视图 ---------- */

function unitListHtml() {
  return DATA.units
    .map((u) =>
      `<a class="card" href="#/${u.id}">
         <div class="row-title">${esc(u.id)} ${esc(u.title)}
           <span style="color:var(--muted);font-weight:400;font-size:13.5px"> ${esc(u.titleZh || "")}</span>
         </div>
         <div class="row-sub">${u.topics.length} 个话题</div>
       </a>`)
    .join("");
}

function renderHome() {
  document.title = "走遍美国 · IELTS 口语话题";
  app.innerHTML =
    `<p class="note">按剧集单元组织的 IELTS 口语话题：先看题自己说，再对照思路与范文。</p>` +
    unitListHtml();
}

function renderIntro() {           // 桌面端首页：内容区给引导卡（导航在左侧栏）
  document.title = "走遍美国 · IELTS 口语话题";
  app.innerHTML =
    `<div class="card">
       <div class="row-title">开始练习</div>
       <div class="row-sub">左侧选单元 → 话题。每题：看题即兴说 1–3 分钟 →
       对照思路提示、词汇，最后展开参考范文（逐句/整段中英对照）。</div>
     </div>`;
}

function renderUnit(unit) {
  document.title = `${unit.id} ${unit.title} · IELTS 口语话题`;
  app.innerHTML =
    `<a class="back" href="#/">← 全部单元</a>
     <h1 class="unit-title">${esc(unit.id)} ${esc(unit.title)}
       <span class="ut-zh">${esc(unit.titleZh || "")}</span></h1>` +
    unit.topics
      .map((t, i) =>
        `<a class="card" href="#/${unit.id}/${t.id}">
           <div class="row-title"><span class="num">${i + 1}</span>${esc(t.zh)}</div>
           <div class="row-sub">${esc(t.question)}</div>
         </a>`)
      .join("");
}

function renderTopic(unit, topic) {
  document.title = `${topic.zh} · ${unit.id} IELTS 口语话题`;
  const hints = topic.hints
    .map(([zh, en]) => `<li>${esc(zh)}<span class="en">${esc(en)}</span></li>`)
    .join("");
  const vocab = topic.vocab
    .map(([en, cn]) => `<span class="chip"><b>${esc(en)}</b> — ${esc(cn)}</span>`)
    .join("");
  app.innerHTML =
    `<a class="back" href="#/${unit.id}">← ${esc(unit.id)} ${esc(unit.title)}</a>
     <div class="q">
       <div class="q-en">${esc(topic.question)}</div>
       <div class="q-zh">${esc(topic.questionZh || "")}</div>
     </div>
     <h2 class="sec">思路提示</h2>
     <ol class="hints">${hints}</ol>
     <h2 class="sec">单元词汇</h2>
     <div class="vocab">${vocab}</div>
     <details class="sample" id="sample">
       <summary>参考范文（先自己说，再看）</summary>
       <div class="tr-toggle">翻译显示：
         <button data-mode="sent" class="${trMode === "sent" ? "sel" : ""}">逐句对照</button>
         <button data-mode="para" class="${trMode === "para" ? "sel" : ""}">整段对照</button>
       </div>
       <div class="body">${sampleHtml(topic.sample, trMode)}</div>
     </details>`;
  app.querySelectorAll(".tr-toggle button").forEach((b) =>
    b.addEventListener("click", () => {
      trMode = b.dataset.mode;
      localStorage.setItem("trMode", trMode);
      renderTopic(unit, topic);          // 重新渲染以切换模式
      const d = document.getElementById("sample");
      if (d) d.open = true;              // 切换时保持展开状态
    }));
}

/* ---------- 侧边栏（桌面） ---------- */

function renderSide(activeUnit, activeTopic) {
  if (!wide.matches) { side.innerHTML = ""; side.onclick = null; return; }
  side.innerHTML = sideHtml(DATA.units, activeUnit, activeTopic, openUnit);
  side.onclick = (e) => {
    const head = e.target.closest(".side-unit-head");
    if (!head) return;                    // 话题链接走默认 hash 跳转
    e.preventDefault();
    const id = head.getAttribute("href").slice(2);
    if (id === openUnit) {
      openUnit = null;                    // 点已展开的：收起
      render();
      return;
    }
    openUnit = id;                        // 展开新的（旧的自动收起）
    if (location.hash === `#/${id}`) render();   // hash 不变就不会触发 hashchange，手动刷
    else location.hash = `#/${id}`;             // 变了则交给 hashchange 渲染，避免双渲染
  };
}

/* ---------- 入口 ---------- */

function render() {
  const { unitId, topicId } = parseHash(location.hash);
  const unit = unitId ? findUnit(DATA, unitId) : null;
  const topic = unit && topicId ? findTopic(unit, topicId) : null;
  if (unit) openUnit = unit.id;           // 深链/切换时当前单元即展开单元

  renderSide(unit ? unit.id : null, topic ? topic.id : null);

  if (!unit) { wide.matches ? renderIntro() : renderHome(); return; }
  if (topic) { renderTopic(unit, topic); return; }
  renderUnit(unit);
}

async function init() {
  DATA = await (await fetch("data/topics.json")).json();
  const m = DATA.meta || {};
  foot.textContent = [m.source, m.band ? `目标 ${m.band} 分` : "", m.note || ""]
    .filter(Boolean).join(" · ");
  window.addEventListener("hashchange", render);
  wide.addEventListener("change", render);
  render();
}

init();
