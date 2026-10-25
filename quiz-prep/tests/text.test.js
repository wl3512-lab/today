const assert = require("assert");
const { plainMath } = require("../lib/text");

assert.strictEqual(plainMath("SE is \\( \\sigma / \\sqrt{n} = 60 / 15 = 4 \\)."), "SE is σ / √(n) = 60 / 15 = 4.");
assert.strictEqual(plainMath("\\( \\sqrt{0.2 \\times 0.8 / 256} = 0.025 \\)"), "√(0.2 × 0.8 / 256) = 0.025");
assert.strictEqual(plainMath("\\( np \\geq 10 \\) and \\( \\hat{p} \\leq 0.3 \\)"), "np ≥ 10 and p̂ ≤ 0.3");
assert.strictEqual(plainMath("\\( \\frac{\\sigma}{\\sqrt{n}} \\), \\( \\bar{x} \\), \\( \\mu_0 \\), \\( \\mu_{0} \\)"), "σ/√(n), x̄, μ₀, μ₀");
assert.strictEqual(plainMath("\\[ P(\\text{Z} > 1.5) \\approx 0.0668 \\]"), "P(Z > 1.5) ≈ 0.0668");
assert.strictEqual(plainMath("no math here"), "no math here");
assert.strictEqual(plainMath(undefined), "");
console.log("text ok");

const { sameAnswer } = require("../lib/text");
assert.ok(sameAnswer("A) -1.28", "A) -1.28"));
assert.ok(sameAnswer("B) −1.28", "-1.28"), "letter and minus sign don't matter");
assert.ok(!sameAnswer("A) ±1.96", "B) ±2"));
assert.ok(sameAnswer("0.6826.", "0.6826"));
assert.ok(!sameAnswer("0.6826", "0.8664"));
assert.ok(!sameAnswer("anything", ""));
console.log("sameAnswer ok");
