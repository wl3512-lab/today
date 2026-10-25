const assert = require("assert");
const { READY_STEPS, doneSteps, readiness } = require("../public/ready.js");

const kit = { cards: [{}, {}, {}], worksheet: { problems: [{ number: 1, parts: [{ label: "a" }, { label: "b" }] }, { number: 2, parts: [] }] } };
assert.strictEqual(READY_STEPS.length, 8);

let r = readiness({}, kit);
assert.deepStrictEqual([r.done, r.total, r.pct, r.next.id], [0, 8, 0, "review"]);

r = readiness({ plan: { review: true, symbols: true } }, kit);
assert.deepStrictEqual([r.pct, r.next.id], [25, "cards1"]);

// flashcards tick themselves once every card is known; the worksheet once every part is marked
assert.ok(doneSteps({ known: [0, 1, 2] }, kit).has("cards1"));
assert.ok(!doneSteps({ known: [0, 1] }, kit).has("cards1"));
assert.ok(doneSteps({ marks: { "Problem 1 a": "right", "Problem 1 b": "wrong", "Problem 2": "wrong" } }, kit).has("ws1"));
assert.ok(!doneSteps({ marks: { "Problem 1 a": "right" } }, kit).has("ws1"), "half marked is not done");
assert.ok(!doneSteps({ known: [] }, { cards: [] }).has("cards1"), "no cards: nothing to finish");

// wrong answers don't lower readiness: doing every step is 100%
const all = Object.fromEntries(READY_STEPS.map((s) => [s.id, true]));
r = readiness({ plan: all, marks: { "Problem 1 a": "wrong" } }, kit);
assert.deepStrictEqual([r.pct, r.next], [100, null]);
console.log("ready ok");
