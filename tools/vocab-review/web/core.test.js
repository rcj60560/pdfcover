import { test } from "node:test";
import assert from "node:assert/strict";
import { newState, answerYes, answerNo, buildQueue, endOfToday, mergeImport } from "./core.js";

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
