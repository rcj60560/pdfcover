// ielts-topics/core.js
// 纯逻辑 + 渲染辅助，无副作用（无 DOM / 网络 / 计时器），node:test 单测。

export function esc(s) {
  return String(s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

export function parseHash(hash) {
  const m = /^#\/([^/]+)(?:\/(.+))?$/.exec(hash || "");
  return m ? { unitId: m[1], topicId: m[2] || null } : { unitId: null, topicId: null };
}

export function findUnit(data, unitId) {
  return (data.units || []).find((u) => u.id === unitId) || null;
}

export function findTopic(unit, topicId) {
  return unit && (unit.topics || []).find((t) => t.id === topicId) || null;
}

// sample = 段落数组，每段是 [en, zh] 句对数组。
// mode "sent"：每句下挂中文；mode "para"：整段英文 + 段下整段中文。
export function sampleHtml(sample, mode) {
  return (sample || []).map((para) => {
    if (mode === "para") {
      const en = para.map(([e]) => esc(e)).join(" ");
      const zh = para.map(([, z]) => esc(z)).join("");
      return `<div class="para"><p class="para-en">${en}</p><p class="para-zh">${zh}</p></div>`;
    }
    const sents = para
      .map(([e, z]) => `<div class="sen">${esc(e)}</div><div class="sen-zh">${esc(z)}</div>`)
      .join("");
    return `<div class="para">${sents}</div>`;
  }).join("");
}

// 桌面端侧边栏：单元手风琴，单一展开（openUnit 为当前展开单元 id 或 null）。
export function sideHtml(units, activeUnit, activeTopic, openUnit) {
  return (units || []).map((u) => {
    const open = u.id === openUnit;
    const topics = open
      ? `<div class="side-topics">${u.topics
          .map((t) =>
            `<a class="side-topic${t.id === activeTopic ? " active" : ""}" href="#/${u.id}/${t.id}">${esc(t.zh)}</a>`)
          .join("")}</div>`
      : "";
    return `<div class="side-unit${open ? " open" : ""}${u.id === activeUnit && !activeTopic ? " active" : ""}">
      <a class="side-unit-head" href="#/${u.id}">${esc(u.id)} ${esc(u.title)}</a>${topics}</div>`;
  }).join("");
}
