import { test } from "node:test";
import assert from "node:assert/strict";
import {
  parseTs, parseSubtitleMd, currentBlockIndex, isEnded, SyncClock, formatMs,
  targetScrollTop,
} from "./core.js";
import { renderBlock, groupManifest, plainText, renderPlain } from "./core.js";

const MD = [
  "# 标题",
  "> 来源：xxx",
  "<style>p{font-size:18px}</style>",
  "",
  "---",
  "",
  "`00:00:00 → 00:00:06`",
  "",
  "**Hello world.**",
  "",
  "你好，世界。",
  "",
  "---",
  "",
  "`3:10 → 3:20`",
  "",
  "**Second block.**",
  "",
  "第二块。",
].join("\n");

test("parseTs 两种格式", () => {
  assert.equal(parseTs("00:00:06"), 6000);
  assert.equal(parseTs("0:06"), 6000);
  assert.equal(parseTs("01:02:03"), 3723000);
  assert.equal(parseTs("3:10"), 190000);
});

test("parseSubtitleMd 标准文档（头部跳过/两种时间戳/rn）", () => {
  const { blocks, hasTimestamps } = parseSubtitleMd(MD.replace(/\n/g, "\r\n"));
  assert.equal(hasTimestamps, true);
  assert.equal(blocks.length, 2);
  assert.deepEqual(blocks[0], {
    startMs: 0, endMs: 6000, en: "Hello world.", zh: "你好，世界。", tsLabel: "00:00:00 → 00:00:06",
  });
  assert.equal(blocks[1].startMs, 190000);
  assert.equal(blocks[1].endMs, 200000);
});

test("parseSubtitleMd 无时间戳降级", () => {
  const { blocks, hasTimestamps } = parseSubtitleMd("# 笔记\n\n普通段落。\n\n---\n\n**加粗**\n");
  assert.equal(hasTimestamps, false);
  assert.deepEqual(blocks, []);
});

test("currentBlockIndex 命中/间隙/首块前/空", () => {
  const B = [{ startMs: 0, endMs: 6000 }, { startMs: 8000, endMs: 14000 }];
  assert.equal(currentBlockIndex(B, 3000), 0);
  assert.equal(currentBlockIndex(B, 7000), 0);      // 间隙保持上一块
  assert.equal(currentBlockIndex(B, 9000), 1);
  assert.equal(currentBlockIndex(B, -1), -1);        // 首块前
  assert.equal(currentBlockIndex([], 1000), -1);
});

test("isEnded", () => {
  const B = [{ startMs: 0, endMs: 6000 }, { startMs: 8000, endMs: 14000 }];
  assert.equal(isEnded(B, 13999), false);
  assert.equal(isEnded(B, 14000), true);
  assert.equal(isEnded([], 999), false);
});

test("targetScrollTop 插值/边界/空", () => {
  const kf = [{ t: 0, y: 100 }, { t: 6000, y: 400 }, { t: 20000, y: 900 }];
  assert.equal(targetScrollTop(-1, kf), 100);       // 首块前
  assert.equal(targetScrollTop(0, kf), 100);
  assert.equal(targetScrollTop(3000, kf), 250);     // 区间线性中点
  assert.equal(targetScrollTop(13000, kf), 650);
  assert.equal(targetScrollTop(99999, kf), 900);    // 末块后保持
  assert.equal(targetScrollTop(500, []), null);     // 无关键帧
  assert.equal(targetScrollTop(6000, [{ t: 6000, y: 1 }, { t: 6000, y: 2 }]), 2); // 同刻
});

test("SyncClock 计时/暂停/±5s/锚定", () => {
  let t = 100000;
  const c = new SyncClock(() => t);
  assert.equal(c.elapsedMs, 0);                      // 未 start
  c.start(0);
  t = 100500;
  assert.equal(c.elapsedMs, 500);
  c.pause();
  t = 101000;
  assert.equal(c.elapsedMs, 500);                    // 暂停期间不走
  c.resume();
  t = 101200;
  assert.equal(c.elapsedMs, 700);
  c.shift(5000);
  assert.equal(c.elapsedMs, 5700);                   // +5s
  c.shift(-10000);
  assert.equal(c.elapsedMs, 0);                      // 负数钳到 0
  t = 101300;
  c.anchorTo(190000);                                // 锚定到 3:10
  t = 101400;
  assert.equal(c.elapsedMs, 190100);
});

test("formatMs", () => {
  assert.equal(formatMs(0), "0:00");
  assert.equal(formatMs(83000), "1:23");
  assert.equal(formatMs(3723000), "1:02:03");
  assert.equal(formatMs(-5), "0:00");
});

test("renderBlock 转义与结构", () => {
  const b = { startMs: 0, endMs: 6, en: "A<B>&C", zh: "甲&乙", tsLabel: "00:00:00 → 00:00:06" };
  const html = renderBlock(b, 3, false);
  assert.ok(html.includes('class="blk" data-i="3"'));
  assert.ok(html.includes('<button class="ts"'));
  assert.ok(html.includes("A&lt;B&gt;&amp;C"));
  assert.ok(html.includes("甲&amp;乙"));
  const on = renderBlock(b, 3, true);
  assert.ok(on.includes('class="blk is-on"'));
  const noZh = renderBlock({ ...b, zh: "" }, 0, false);
  assert.ok(!noZh.includes('class="zh"'));
});

test("plainText 英空格拼接/中文直接拼接", () => {
  const { blocks } = parseSubtitleMd(MD);
  const pt = plainText(blocks);
  assert.equal(pt.en, "Hello world. Second block.");
  assert.equal(pt.zh, "你好，世界。第二块。");
  assert.deepEqual(plainText([]), { en: "", zh: "" });
});

test("renderPlain 英中分开/复制按钮/转义/无中文省略", () => {
  const html = renderPlain({ en: "A<B>", zh: "甲" });
  assert.equal((html.match(/class="plain-part"/g) || []).length, 2);   // 英文/中文两张卡片
  assert.ok(html.includes('class="copy-btn" data-copy="en"'));
  assert.ok(html.includes('class="copy-btn" data-copy="zh"'));
  assert.ok(html.includes("A&lt;B&gt;"));
  assert.ok(html.includes('class="plain-zh"'));
  const noZh = renderPlain({ en: "E", zh: "" });
  assert.ok(!noZh.includes("plain-zh"));
  assert.equal((noZh.match(/class="plain-part"/g) || []).length, 1);
});

test("groupManifest 按目录分组", () => {
  const groups = groupManifest([
    { path: "in-use/Unit 1.md", title: "Unit 1", count: 3, duration: 20 },
    { path: "collins/A.md", title: "A", count: 2, duration: 14 },
    { path: "root.md", title: "root", count: 1, duration: 6 },
  ]);
  // 空串目录（根目录）排序在最前，显示名替换为「字幕」
  assert.deepEqual(groups.map((g) => g.dir), ["字幕", "collins", "in-use"]);
  assert.equal(groups[0].items.length, 1);
});
