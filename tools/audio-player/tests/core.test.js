import { test } from "node:test";
import assert from "node:assert/strict";
import {
  parseBooks, parseTracks, sortTracks,
  cycleLoop, cycleSpeed, nextTrack, clampSeek,
  formatTime, renderBookCard, renderTrackRow,
  renderLinkCard, isLocalHost, topicsHref,
} from "../core.js";

test("parseBooks keeps directories only", () => {
  const entries = [
    { name: "book1", type: "directory" },
    { name: "readme.txt", type: "file" },
    { name: "book2", type: "directory" },
  ];
  assert.deepEqual(parseBooks(entries), ["book1", "book2"]);
});

test("parseBooks tolerates non-array", () => {
  assert.deepEqual(parseBooks(null), []);
  assert.deepEqual(parseBooks(undefined), []);
});

test("parseBooks sorts IELTS issues numerically", () => {
  const entries = [
    { name: "剑桥雅思19", type: "directory" },
    { name: "剑桥雅思2", type: "directory" },
    { name: "剑桥雅思10", type: "directory" },
  ];
  assert.deepEqual(parseBooks(entries), ["剑桥雅思2", "剑桥雅思10", "剑桥雅思19"]);
});

test("parseTracks keeps mp3 files only (case-insensitive)", () => {
  const entries = [
    { name: "001.mp3", type: "file" },
    { name: "001.txt", type: "file" },
    { name: "sub", type: "directory" },
    { name: "002.MP3", type: "file" },
  ];
  assert.deepEqual(parseTracks(entries), ["001.mp3", "002.MP3"]);
});

test("sortTracks numeric order for unpadded", () => {
  assert.deepEqual(sortTracks(["10.mp3", "2.mp3", "1.mp3"]), ["1.mp3", "2.mp3", "10.mp3"]);
});

test("sortTracks zero-padded order", () => {
  assert.deepEqual(sortTracks(["020.mp3", "001.mp3", "002.mp3"]), ["001.mp3", "002.mp3", "020.mp3"]);
});

test("sortTracks does not mutate input", () => {
  const input = ["2.mp3", "1.mp3"];
  sortTracks(input);
  assert.deepEqual(input, ["2.mp3", "1.mp3"]);
});

test("cycleLoop off->one->all->off", () => {
  assert.equal(cycleLoop("off"), "one");
  assert.equal(cycleLoop("one"), "all");
  assert.equal(cycleLoop("all"), "off");
});

test("cycleSpeed cycles and resets unknown", () => {
  assert.equal(cycleSpeed(1), 1.25);
  assert.equal(cycleSpeed(1.25), 1.5);
  assert.equal(cycleSpeed(1.5), 0.75);
  assert.equal(cycleSpeed(0.75), 1);
  assert.equal(cycleSpeed(999), 1);
});

test("nextTrack off stops at end", () => {
  assert.equal(nextTrack(0, 3, "off"), 1);
  assert.equal(nextTrack(2, 3, "off"), null);
});

test("nextTrack one repeats current", () => {
  assert.equal(nextTrack(2, 3, "one"), 2);
});

test("nextTrack all wraps to 0", () => {
  assert.equal(nextTrack(2, 3, "all"), 0);
});

test("clampSeek clamps to [0,duration]", () => {
  assert.equal(clampSeek(-5, 100), 0);
  assert.equal(clampSeek(200, 100), 100);
  assert.equal(clampSeek(50, 100), 50);
  assert.equal(clampSeek(50, 0), 0);
  assert.equal(clampSeek(50, NaN), 0);
});

test("formatTime m:ss", () => {
  assert.equal(formatTime(0), "0:00");
  assert.equal(formatTime(65), "1:05");
  assert.equal(formatTime(NaN), "0:00");
});

test("renderBookCard embeds name and count", () => {
  const html = renderBookCard("剑桥10", 20);
  assert.match(html, /data-book="剑桥10"/);
  assert.match(html, /剑桥10/);
  assert.match(html, /20集/);
});

test("renderBookCard omits count when not a number", () => {
  const html = renderBookCard("书", NaN);
  assert.doesNotMatch(html, /集/);
});

test("renderTrackRow marks current only when asked", () => {
  assert.doesNotMatch(renderTrackRow("001.mp3", 0, false), /is-current/);
  assert.match(renderTrackRow("002.mp3", 1, true), /is-current/);
  assert.match(renderTrackRow("002.mp3", 1, true), /data-index="1"/);
});

test("renderTrackRow labels normalized test and part names", () => {
  assert.match(renderTrackRow("T03-P04.mp3", 0, false), /Test 3 · Part 4/);
  assert.match(renderTrackRow("T02.mp3", 0, false), /Test 2/);
});

test("renderBookCard escapes special chars", () => {
  const html = renderBookCard('a"<b>', 1);
  assert.doesNotMatch(html, /data-book="a"<b>"/); // 引号被转义，不破坏属性
  assert.match(html, /&quot;/);
});

test("renderLinkCard 外链卡片：新页签 + 转义", () => {
  const html = renderLinkCard("http://127.0.0.1:8500", '走遍美国<口语>', "188 个话题");
  assert.match(html, /href="http:\/\/127\.0\.0\.1:8500"/);
  assert.match(html, /target="_blank"/);
  assert.match(html, /rel="noopener"/);
  assert.match(html, /&lt;口语&gt;/);          // 标题转义
  assert.doesNotMatch(html, /<口语>/);
  assert.match(html, /188 个话题/);
});

test("isLocalHost 仅本机地址显示外链卡片", () => {
  assert.equal(isLocalHost("127.0.0.1"), true);
  assert.equal(isLocalHost("localhost"), true);
  assert.equal(isLocalHost("192.168.1.5"), false);   // --lan 手机访问也不显示
  assert.equal(isLocalHost("47.108.230.162"), false);
});

test("topicsHref 按访问环境返回话题工具地址", () => {
  assert.equal(topicsHref("127.0.0.1"), "http://127.0.0.1:8500");   // 本机 → 本地工具
  assert.equal(topicsHref("localhost"), "http://127.0.0.1:8500");
  assert.equal(topicsHref("47.108.230.162"), "topics/");            // 线上 → 部署路径（相对 /script/）
  assert.equal(topicsHref("192.168.1.5"), null);                    // 局域网手机 → 不显示
});
