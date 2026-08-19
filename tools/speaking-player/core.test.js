import { test } from "node:test";
import assert from "node:assert/strict";
import {
  parseTracks, sortTracks, currentWordIndex, currentSentenceIndex,
  sentenceRange, clampSeek, formatTime, renderTrackRow, renderSentence,
} from "./core.js";

const WORDS = [
  { t: "To", s: 0, d: 200 }, { t: "me,", s: 240, d: 180 },
  { t: "world.", s: 500, d: 300 },
];

test("parseTracks 配对 json", () => {
  const tracks = parseTracks([
    { name: "话题1.mp3", type: "file" }, { name: "话题1.json", type: "file" },
    { name: "旧.mp3", type: "file" }, { name: "note.txt", type: "file" },
    { name: "子目录", type: "directory" },
  ]);
  assert.deepEqual(tracks, [
    { file: "话题1.mp3", name: "话题1", hasSubtitle: true },
    { file: "旧.mp3", name: "旧", hasSubtitle: false },
  ]);
});

test("sortTracks 数字自然排序", () => {
  const t = (n) => ({ file: n, name: n, hasSubtitle: false });
  assert.deepEqual(
    sortTracks([t("话题10.mp3"), t("话题2.mp3"), t("话题1.mp3")]).map((x) => x.file),
    ["话题1.mp3", "话题2.mp3", "话题10.mp3"],
  );
});

test("currentWordIndex 二分与边界", () => {
  assert.equal(currentWordIndex(WORDS, 0), 0);
  assert.equal(currentWordIndex(WORDS, 300), 1);     // 间隙时停在上一词
  assert.equal(currentWordIndex(WORDS, 799), 2);
  assert.equal(currentWordIndex(WORDS, 800), 2);     // 句尾停最后一词
  assert.equal(currentWordIndex(WORDS, -1), -1);
});

test("currentSentenceIndex / sentenceRange", () => {
  const S = [{ i: 0, j: 1, start: 0, end: 420 }, { i: 2, j: 2, start: 500, end: 800 }];
  assert.equal(currentSentenceIndex(S, 100), 0);
  assert.equal(currentSentenceIndex(S, 600), 1);
  assert.equal(currentSentenceIndex(S, 900), 1);
  assert.deepEqual(sentenceRange(S, 1), { start: 500, end: 800 });
  assert.equal(sentenceRange(S, 9), null);
});

test("clampSeek / formatTime", () => {
  assert.equal(clampSeek(-1, 10), 0);
  assert.equal(clampSeek(11, 10), 10);
  assert.equal(formatTime(83), "1:23");
});

test("renderTrackRow 转义与状态", () => {
  const html = renderTrackRow({ file: "a&b.mp3", name: "a&b", hasSubtitle: true }, 0, true);
  assert.ok(html.includes("a&amp;b"));
  assert.ok(html.includes("is-current"));
  assert.ok(html.includes("data-index=\"0\""));
});

test("renderSentence 高亮 class", () => {
  const html = renderSentence(WORDS, 0, 2, 1);
  assert.ok(html.includes('data-w="1"'));
  assert.ok(html.includes("w-on"));
  assert.ok(html.includes("w-done"));
  assert.ok(!renderSentence(WORDS, 0, 2, -1).includes("w-on"));
});
