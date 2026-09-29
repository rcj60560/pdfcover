import { test } from "node:test";
import assert from "node:assert/strict";
import { newState, answerYes, answerNo, buildQueue, endOfToday, mergeImport, logJudge, summarize, wordGroups } from "./core.js";

const DAY = 86400000;
test("认识:间隔 1→3→×ease,连认4次毕业", () => {
  let s = newState();
  s = answerYes(s, 0);       assert.equal(s.i, 1);  assert.equal(s.g, false);
  s = answerYes(s, s.due);   assert.equal(s.i, 3);  assert.equal(s.g, false);
  s = answerYes(s, s.due);   assert.equal(s.i, Math.round(3 * 2.5));
  s = answerYes(s, s.due);   assert.equal(s.g, true);
});

test("不认识:重置间隔、降 ease、10分钟后重现", () => {
  let s = answerYes(answerYes(newState(), 0), DAY);
  s = answerNo(s, 2 * DAY);
  assert.equal(s.i, 0); assert.equal(s.r, 0);
  assert.equal(s.e, 2.3); assert.equal(s.due - 2 * DAY, 600000);
});

test("队列:到期复习在前,新词受每日上限", () => {
  const now = Date.now();  // 测试内可用固定数:用 endOfToday 语义断言
  const t = 1700000000000;
  const states = {
    due: { ...newState(), r: 1, i: 1, due: t - DAY },        // 到期
    future: { ...newState(), due: t + 10 * DAY },             // 未到期
    grad: { ...newState(), g: true },                          // 已毕业
  };
  const { queue, newToday } = buildQueue(["due", "future", "grad", "n1", "n2", "n3"],
    states, t, 2, { lastNewDate: "", lastNewCount: 0 });
  assert.deepEqual(queue, ["due", "n1", "n2"]);
  assert.equal(newToday, 2);
  const next = buildQueue(["due", "n3"], states, t, 2,
    { lastNewDate: new Date(t).toDateString(), lastNewCount: 2 });
  assert.deepEqual(next.queue, ["due"]);   // 当日上限已用完
});

test("endOfToday 返回当天 24:00", () => {
  const t = new Date("2026-09-28T09:00:00").getTime();
  assert.equal(endOfToday(t), new Date("2026-09-28T23:59:59.999").getTime());
});

test("mergeImport 以导入为准且校验结构", () => {
  const cur = { states: { a: newState() }, meta: { lastNewDate: "", lastNewCount: 0 } };
  const imp = { states: { b: { ...newState(), r: 2 } }, meta: { lastNewDate: "x", lastNewCount: 5 } };
  const merged = mergeImport(cur, imp);
  assert.deepEqual(Object.keys(merged.states), ["b"]);
  assert.equal(merged.meta.lastNewCount, 5);
  assert.throws(() => mergeImport(cur, { states: null }), /格式不对/);
});

test("logJudge:按日记录 y/n、累计计数,旧 meta 缺字段可兼容且不被就地修改", () => {
  const t = new Date("2026-09-28T10:00:00").getTime();
  let meta = { lastNewDate: "", lastNewCount: 3 };  // 旧版本 meta 无 dailyLog/计数
  meta = logJudge(meta, t, true);
  meta = logJudge(meta, t, false);
  assert.deepEqual(meta.dailyLog["2026-09-28"], { y: 1, n: 1 });
  assert.equal(meta.totalYes, 1); assert.equal(meta.totalNo, 1);
  assert.equal(meta.lastNewCount, 3);               // 原有字段保留
  meta = logJudge(meta, t + 2 * 3600000, true);     // 同日再判
  assert.deepEqual(meta.dailyLog["2026-09-28"], { y: 2, n: 1 });
  const next = logJudge(meta, t + 26 * 3600000, true);  // 次日
  assert.deepEqual(next.dailyLog["2026-09-29"], { y: 1, n: 0 });
  assert.equal(next.totalYes, 3); assert.equal(next.totalNo, 1);
  assert.equal("2026-09-29" in meta.dailyLog, false);   // 返回新对象,原 meta 未动
});

test("summarize:词池四态/今日判定/累计正确率/近7日趋势", () => {
  const t = new Date("2026-09-28T09:00:00").getTime();
  let meta = {};
  meta = logJudge(meta, t - DAY, false);            // 昨日 1 不认识
  meta = logJudge(meta, t, true);
  meta = logJudge(meta, t, true);
  meta = logJudge(meta, t, false);                  // 今日 2 认识 1 不认识
  const states = {
    a: { ...newState(), g: true },                  // 已毕业
    b: { ...newState(), r: 2 },                     // 学习中(连对过)
    d: { ...newState(), r: 0 },                     // 学习中(刚答错)
    orphan: { ...newState(), g: true },             // 词池之外的状态不计入
  };
  const s = summarize(["a", "b", "c", "d"], states, meta, { candidate: 10, known: 5 }, t);
  assert.equal(s.total, 15);                        // 词池 = candidate + known
  assert.equal(s.graduated, 1);
  assert.equal(s.learning, 2);
  assert.equal(s.notStarted, 1);                    // c 无状态
  assert.equal(s.todayYes, 2); assert.equal(s.todayNo, 1);
  assert.equal(s.totalYes, 2); assert.equal(s.totalNo, 2);   // 含昨日 1 张不认识
  assert.equal(s.accuracy, 0.5);
  assert.equal(s.trend.length, 7);                  // 近 7 日含今日,旧→新
  assert.deepEqual(s.trend[6], { key: "2026-09-28", y: 2, n: 1 });
  assert.deepEqual(s.trend[5], { key: "2026-09-27", y: 0, n: 1 });
  assert.deepEqual(s.trend[0], { key: "2026-09-22", y: 0, n: 0 });  // 无记录日补零
});

test("summarize:空进度与无 stats 时兜底", () => {
  const t = new Date("2026-09-28T09:00:00").getTime();
  const s = summarize(["x"], {}, {}, undefined, t);
  assert.equal(s.total, 1);                         // 无 vocabStats → 用词数
  assert.equal(s.notStarted, 1);
  assert.equal(s.todayYes, 0); assert.equal(s.todayNo, 0);
  assert.equal(s.accuracy, 0);                      // 无判定不除零
});

test("wordGroups:字母分节/组内排序/空字母跳过/# 兜底", () => {
  const states = {
    apple: { ...newState(), g: true },              // 已毕业
    apron: { ...newState(), r: 1 },                 // 学习中
    banana: { ...newState() },                      // 学习中(答过但未毕业)
  };
  const r = wordGroups(["banana", "apple", "apricot", "apron", "Cherry", "2nd", "空调"], states);
  assert.deepEqual(r.groups.map((g) => g.letter), ["A", "B", "C", "#"]);   // 无词的字母不出现,# 殿后
  assert.deepEqual(r.groups[0].items, [
    { w: "apple", status: "done" },                 // g=true → done
    { w: "apricot", status: "fresh" },              // 无状态 → fresh
    { w: "apron", status: "learning" },             // 有状态未毕业 → learning
  ]);
  assert.deepEqual(r.groups[3].items, [{ w: "2nd", status: "fresh" }, { w: "空调", status: "fresh" }]);
});

test("wordGroups:四态计数与空词表", () => {
  const states = {
    a: { ...newState(), g: true },
    b: { ...newState() },
  };
  const r = wordGroups(["a", "b", "c", "d"], states);
  assert.deepEqual(r.counts, { total: 4, done: 1, learning: 1, fresh: 2 });
  const empty = wordGroups([], {});
  assert.deepEqual(empty.counts, { total: 0, done: 0, learning: 0, fresh: 0 });
  assert.deepEqual(empty.groups, []);
});
