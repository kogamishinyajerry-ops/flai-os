import test from "node:test";
import assert from "node:assert/strict";
import { inlineSegs } from "../src/utils/mdInline.js";

const strongOf = (segs) => segs.filter((segment) => segment.t === "strong").map((segment) => segment.s);
const textLeaks = (segs) => segs.some((segment) => segment.t === "text" && segment.s.includes("**"));

test("GLM witness: Chinese strong markers pair without leaking asterisks", () => {
  const lines = [
    "先帮你理清一下。平台里确实有一个**性能盘批量计算 Agent**（`performance_disk_agent`），它能\"上传算例表",
    "但有件事必须先跟你说清楚：**这个 Agent 目前处于模拟阶段**，计算用的是占位公式（纯属虚构），输出**没有任何工程意义**。",
    "1. **你的\"裕度核对\"具体是怎么个核对法？** 比如：拿每个工况点的实测参数去跟设计限值做比对",
    "2. **数据是什么形态？** 一个 Excel 表里很多算例/工况点",
  ];

  for (const line of lines) {
    const segs = inlineSegs(line);
    assert.equal(textLeaks(segs), false, `asterisk leak: ${line.slice(0, 40)}`);
    assert.ok(strongOf(segs).length >= 1, `expected strong segment: ${line.slice(0, 40)}`);
  }

  const first = inlineSegs(lines[0]);
  assert.deepEqual(strongOf(first), ["性能盘批量计算 Agent"]);
  assert.ok(first.some((segment) => segment.t === "code" && segment.s === "performance_disk_agent"));
});

test("strong markers pair next to Chinese punctuation", () => {
  assert.deepEqual(strongOf(inlineSegs("结论：**关键**是收敛")), ["关键"]);
  assert.deepEqual(strongOf(inlineSegs("（**重点**）全角括号")), ["重点"]);
  assert.deepEqual(strongOf(inlineSegs("「**引号内**」")), ["引号内"]);
  assert.deepEqual(strongOf(inlineSegs("**目标**：完成三件事")), ["目标"]);
});

test("Python kwargs and exponentiation remain literal text", () => {
  const kwargs = inlineSegs("def f(**kwargs) 与 **重要** 共存");
  assert.deepEqual(strongOf(kwargs), ["重要"]);
  assert.ok(kwargs.some((segment) => segment.t === "text" && segment.s.includes("f(**kwargs)")));

  const exponentiation = inlineSegs("x = 2 ** 3 的结果");
  assert.deepEqual(strongOf(exponentiation), []);
  assert.ok(exponentiation.some((segment) => segment.t === "text" && segment.s.includes("2 ** 3")));
});

test("unpaired markers remain literal text", () => {
  const segs = inlineSegs("只有开没有闭 **悬空");
  assert.deepEqual(strongOf(segs), []);
  assert.ok(segs.some((segment) => segment.t === "text" && segment.s.includes("**悬空")));
});
