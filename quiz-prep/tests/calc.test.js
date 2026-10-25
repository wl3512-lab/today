const assert = require("assert");
const { runCalc } = require("../lib/calc");

// Slide 10: soda cans. σx̄ = 0.5/10 = 0.05, z = −0.15/0.05 = −3 < −1.65 → reject
const soda = runCalc({ type: "z-test-mean", claim: 12, xbar: 11.85, sd: 0.5, n: 100, alpha: 0.05, tail: "left",
  ifReject: "The cans hold less than 12 oz.", ifFail: "Not enough evidence." });
assert.strictEqual(soda.z, -3);
assert.strictEqual(soda.reject, true);
assert.ok(soda.steps.some((s) => s.includes("0.5/√100 = 0.5/10 = 0.05")), soda.steps.join(" | "));
assert.ok(soda.steps.some((s) => s.includes("−1.65")));
assert.ok(soda.answer.startsWith("Reject H₀") && soda.answer.includes("less than 12 oz"));
assert.deepStrictEqual([soda.diagram.shade, soda.diagram.cut, soda.diagram.mark, soda.diagram.mean, soda.diagram.se], ["left", 1.65, -3, 12, 0.05]);
assert.strictEqual(soda.check.choices[soda.check.answer], "−3");
assert.strictEqual(new Set(soda.check.choices).size, soda.check.choices.length, "no duplicate choices");

// Slide 11: steel rods, two-tailed. σx̄ = 0.08/8 = 0.01, z = 1.5, |1.5| < 2 → fail to reject
const rods = runCalc({ type: "z-test-mean", claim: 36, xbar: 36.015, sd: 0.08, n: 64, alpha: 0.05, tail: "two" });
assert.strictEqual(rods.z, 1.5);
assert.strictEqual(rods.reject, false);
assert.ok(rods.answer.startsWith("Fail to reject H₀"));
assert.strictEqual(rods.diagram.shade, "both");
assert.strictEqual(rods.diagram.areaLabel, "α/2 = 0.025");

// Slide 12: SmileX. σp̂ = √(0.2·0.8/400) = 0.02, z = −1.5 < −1.28 (α = 0.1 one-tailed) → reject
const smile = runCalc({ type: "z-test-prop", claim: 0.2, phat: 0.17, n: 400, alpha: 0.1, tail: "left" });
assert.strictEqual(smile.z, -1.5);
assert.strictEqual(smile.reject, true);
// Slide 13: toy cars. p̂ = 45/225 = 0.2, σp̂ = 0.3/15 = 0.02, z = 5 > 2.33 → reject (the AI said 3)
const cars = runCalc({ type: "z-test-prop", claim: 0.1, count: 45, n: 225, alpha: 0.01, tail: "right" });
assert.strictEqual(cars.z, 5);
assert.strictEqual(cars.reject, true);
assert.ok(cars.steps[0].includes("45/225 = 0.2"));

// Lesson 9: CIs and sample size
const ci = runCalc({ type: "ci-mean", xbar: 500, sd: 75, n: 900, level: 95 });
assert.deepStrictEqual([ci.lo, ci.hi, ci.E], [495, 505, 5]);
assert.deepStrictEqual([ci.diagram.type, ci.diagram.center, ci.diagram.margin], ["interval", 500, 5]);
const cip = runCalc({ type: "ci-prop", count: 50, n: 100, level: 95 });
assert.deepStrictEqual([cip.lo, cip.hi], [0.4, 0.6]);
assert.strictEqual(runCalc({ type: "size-mean", sd: 26, E: 1, level: 95 }).n, 2704);

// bad input
assert.strictEqual(runCalc({ type: "z-test-mean", claim: 12, xbar: 11.85, sd: 0, n: 100, alpha: 0.05, tail: "left" }), null);
assert.strictEqual(runCalc({ type: "z-test-mean", claim: 12, xbar: 11.85, sd: 0.5, n: 100, alpha: 0.07, tail: "left" }), null, "α not in the course table");
assert.strictEqual(runCalc({ type: "z-test-prop", claim: 1.2, phat: 0.5, n: 100, alpha: 0.05, tail: "two" }), null);
assert.strictEqual(runCalc({ type: "ci-mean", xbar: 1, sd: 1, n: 4, level: 80 }), null);
assert.strictEqual(runCalc({ type: "anova" }), null);
console.log("calc ok");
