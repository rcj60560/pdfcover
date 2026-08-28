import { test } from "node:test";
import assert from "node:assert/strict";
import { parseHash, findUnit, findTopic, esc, sampleHtml, sideHtml } from "./core.js";

const DATA = {
  units: [
    { id: "U01", title: "Rebecca's Dream", titleZh: "丽贝卡的梦想", topics: [
      { id: "U01-1", zh: "坚持追梦" },
      { id: "U01-2", zh: "别人质疑你的计划" },
    ]},
    { id: "U40", title: "Sharing Feelings", titleZh: "分享感受", topics: [
      { id: "U40-1", zh: "朋友帮你渡过压力期" },
      { id: "U40-2", zh: "父母不赞成的决定" },
    ]},
  ],
};

test("parseHash 解析路由", () => {
  assert.deepEqual(parseHash("#/U40/U40-2"), { unitId: "U40", topicId: "U40-2" });
  assert.deepEqual(parseHash("#/U40"), { unitId: "U40", topicId: null });
  assert.deepEqual(parseHash(""), { unitId: null, topicId: null });
  assert.deepEqual(parseHash("#/"), { unitId: null, topicId: null });
});

test("findUnit/findTopic 命中与未命中", () => {
  const u = findUnit(DATA, "U40");
  assert.equal(u.title, "Sharing Feelings");
  assert.equal(findUnit(DATA, "U99"), null);
  assert.equal(findTopic(u, "U40-2").zh, "父母不赞成的决定");
  assert.equal(findTopic(u, "U40-9"), null);
});

test("esc 转义 html", () => {
  assert.equal(esc(`<b>"Rebecca's"</b>`),
    "&lt;b&gt;&quot;Rebecca&#39;s&quot;&lt;/b&gt;");
});

const SAMPLE = [
  [["Hello world.", "你好，世界。"], ["Nice day.", "好天气。"]],
  [["Second para.", "第二段。"]],
];

test("sampleHtml 逐句模式：每句下挂翻译", () => {
  const html = sampleHtml(SAMPLE, "sent");
  assert.ok(html.includes("Hello world."));
  assert.ok(html.includes("你好，世界。"));
  assert.ok(html.includes("class=\"sen\""));
  assert.ok(html.includes("class=\"sen-zh\""));
  // 两段各自成块
  assert.equal((html.match(/class="para"/g) || []).length, 2);
});

test("sampleHtml 整段模式：段落后跟整段翻译", () => {
  const html = sampleHtml(SAMPLE, "para");
  assert.ok(html.includes("Hello world. Nice day."));
  assert.ok(html.includes("你好，世界。好天气。"));
  assert.ok(!html.includes("sen-zh"));
});

test("sampleHtml 转义与段落分组", () => {
  const html = sampleHtml([[["<b>hi</b>", "中文"]]], "sent");
  assert.ok(html.includes("&lt;b&gt;hi&lt;/b&gt;"));
});

test("sideHtml 侧边栏树：单一展开、高亮、转义", () => {
  const open = sideHtml(DATA.units, "U40", "U40-2", "U40");
  // 只有 openUnit 展开显示话题链接；其余单元收起
  assert.ok(open.includes('href="#/U40/U40-2"'));
  assert.ok(!open.includes('href="#/U01/U01-1"'));
  // 当前话题高亮
  assert.ok(open.includes("active"));
  assert.ok(open.includes("Sharing Feelings"));
  // 换一个展开单元：U40 的话题消失，U01 的出现
  const other = sideHtml(DATA.units, "U01", null, "U01");
  assert.ok(!other.includes('href="#/U40/U40-2"'));
  assert.ok(other.includes('href="#/U01/U01-1"'));
});
