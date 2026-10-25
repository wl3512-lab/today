const assert = require("assert");
const { markedParts, focusPlan } = require("../lib/marks");

const ws = { problems: [
  { number: 1, text: "Cans hold μ = 12 oz.", parts: [{ label: "a", text: "Find σx̄." }, { label: "b", text: "Find P(x̄ < 11.8)." }] },
  { number: 2, text: "A poll of 400 people.", parts: [] }
] };
const got = markedParts(ws, { "Problem 1 a": "right", "Problem 1 b": "wrong", "Problem 2": "wrong" });
assert.deepStrictEqual(got.missed, ["Cans hold μ = 12 oz. Find P(x̄ < 11.8).", "A poll of 400 people."]);
assert.deepStrictEqual(got.right, ["Cans hold μ = 12 oz. Find σx̄."]);
assert.deepStrictEqual(markedParts(null, { "Problem 1 a": "wrong" }), { missed: [], right: [] });

assert.strictEqual(focusPlan(0, 0), null);                                  // no marks: as before
assert.deepStrictEqual(focusPlan(4, 6), { missed: 4, kept: 2, fresh: 0 });  // her sheet today
assert.deepStrictEqual(focusPlan(1, 9), { missed: 2, kept: 2, fresh: 2 });  // one miss still gets 2 tries
assert.deepStrictEqual(focusPlan(9, 0), { missed: 4, kept: 0, fresh: 2 });
assert.deepStrictEqual(focusPlan(0, 5), { missed: 0, kept: 2, fresh: 4 });
console.log("marks ok");

const { mixOff } = require("../lib/marks");
const probs = (...f) => f.map((focus) => ({ focus }));
assert.strictEqual(mixOff(probs("missed", "missed", "missed", "missed", "kept", "kept"), { missed: 4, kept: 2, fresh: 0 }), 0);
assert.strictEqual(mixOff(probs("missed", "missed", "missed", "kept", "kept", "kept"), { missed: 4, kept: 2, fresh: 0 }), 2);
assert.strictEqual(mixOff(probs("new", "new"), null), 0);
console.log("mixOff ok");
