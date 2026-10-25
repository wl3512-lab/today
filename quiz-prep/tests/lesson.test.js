const assert = require("assert");
const { cleanLesson, cleanDiagram } = require("../lib/lesson");

const chunk = (over = {}) => ({
  title: "What α means", idea: "α is how often you reject a true H₀.",
  diagram: { type: "bell", shade: "left", cut: 1.65, areaLabel: "α = 0.05" },
  example: { problem: "α = 0.05, one-tailed left", steps: ["Look up the cutoff", "z = −1.65"], answer: "−1.65" },
  hook: "α = false alarm rate", check: { q: "α is…", choices: ["P(reject | H₀ true)", "P(H₀ true)", "the p-value"], answer: 0, why: "It is the false alarm rate." },
  page: 4, ...over
});
const raw = {
  title: " Hypothesis Testing ",
  recap: { lesson: 9, title: "Confidence Intervals", rule: "x̄ ± z·σ/√n", diagram: { type: "interval", center: 50, margin: 4, centerLabel: "x̄ = 50" },
    recall: [{ q: "What does 95% mean?", a: "95% of intervals catch μ." }] },
  chunks: [chunk(), chunk({ title: "The test statistic", diagram: { type: "bell", shade: "left", cut: 9 } }),
    chunk({ title: "Decide", check: { q: "?", choices: ["a", "b"], answer: 5, why: "" } }),
    chunk({ title: "LaTeX", idea: "SE is \\( \\sigma / \\sqrt{n} \\)", page: "4" })]
};
const L = cleanLesson(raw, { number: 10, prevNumber: 9 });
assert.strictEqual(L.title, "Hypothesis Testing");
assert.strictEqual(L.chunks.length, 4);
assert.strictEqual(L.chunks[0].diagram.type, "bell");
assert.strictEqual(L.chunks[1].diagram, null, "cut 9 is dropped, chunk kept");
assert.strictEqual(L.chunks[1].title, "The test statistic");
assert.strictEqual(L.chunks[2].check, null, "answer index out of range drops the check");
assert.strictEqual(L.chunks[3].idea, "SE is σ / √(n)");
assert.strictEqual(L.chunks[3].page, 4, "numeric strings become page numbers");
assert.strictEqual(L.recap.lesson, 9);
assert.strictEqual(L.recap.diagram.type, "interval");

// no previous lesson: no recap even if the AI wrote one
assert.strictEqual(cleanLesson(raw, { number: 10, prevNumber: null }).recap, null);
// clipped to 8
assert.strictEqual(cleanLesson({ ...raw, chunks: Array.from({ length: 11 }, () => chunk()) }, { number: 10, prevNumber: 9 }).chunks.length, 8);
// too thin
assert.throws(() => cleanLesson({ ...raw, chunks: [chunk(), chunk({ idea: "" })] }, { number: 10, prevNumber: 9 }), /too thin/);

// diagrams
assert.strictEqual(cleanDiagram({ type: "flow", steps: ["only one"] }), null);
assert.deepStrictEqual(cleanDiagram({ type: "flow", steps: ["a", " b ", ""] }), { type: "flow", steps: ["a", "b"] });
assert.strictEqual(cleanDiagram({ type: "interval", center: 1, margin: -2 }), null);
assert.strictEqual(cleanDiagram({ type: "bell", shade: "left", cut: 1.65, mark: 50 }).mark, null, "a silly mark is dropped, the curve stays");
assert.strictEqual(cleanDiagram({ type: "bell", shade: "right", cut: 2.33, mark: 5 }).mark, 5, "z = 5 is kept (drawn off the chart)");
assert.strictEqual(cleanDiagram({ type: "compare", columns: [{ head: "A", items: ["x"] }] }), null);
assert.strictEqual(cleanDiagram({ type: "formula", parts: [{ text: "z", role: "weird" }, { text: "=", role: "op" }] }).parts[0].role, "op");
assert.strictEqual(cleanDiagram({ type: "map" }), null);
console.log("lesson ok");

const { lessonGaps } = require("../lib/lesson");
const full = { chunks: Array.from({ length: 7 }, (_, i) => ({ ...chunk({ title: "c" + i, hook: "hook " + i,
  diagram: { type: "bell", shade: "left", cut: 1.65, areaLabel: "α = 0.05", mark: -3 },
  example: { problem: "p", steps: ["z = −3"], answer: "Reject H₀" } }), computed: true })) };
assert.deepStrictEqual(lessonGaps(full), []);
const { PROMPT_HOOKS } = require("../lib/lesson");
const thin = { chunks: [chunk({ diagram: null, hook: PROMPT_HOOKS[0] }), chunk({ diagram: null }), chunk({ diagram: null,
  example: { problem: "SmileX", steps: ["H₀: p = 0.2"], answer: "Test if the share is less than 20%." } })] };
const gaps = lessonGaps(thin);
assert.ok(gaps.some((g) => /3 chunks/.test(g)), "too few chunks");
assert.ok(gaps.some((g) => /diagram/.test(g)), "too few diagrams");
assert.ok(gaps.some((g) => /SmileX/.test(g)), "unfinished example named");
assert.ok(gaps.some((g) => /copied/.test(g)), "copied hook");
console.log("lessonGaps ok");

// a worked example given as numbers is computed by the app: steps, answer, curve and check all replaced
const calcd = cleanLesson({ title: "t", chunks: [chunk(), chunk(), chunk({ title: "Toy cars",
  diagram: { type: "flow", steps: ["a", "b"] }, check: { q: "z?", choices: ["3", "5"], answer: 0, why: "" },
  example: { problem: "Does the machine need adjusting?", calc: { type: "z-test-prop", claim: 0.1, count: 45, n: 225, alpha: 0.01, tail: "right", ifReject: "Adjust it." } } })] },
  { number: 10, prevNumber: 9 });
const cars = calcd.chunks[2];
assert.ok(cars.computed && cars.example.answer.startsWith("Reject H₀. Adjust it."));
assert.ok(cars.example.steps.some((s) => s.includes("= 5")));
assert.strictEqual(cars.diagram.type, "bell"); assert.strictEqual(cars.diagram.mark, 5);
assert.strictEqual(cars.check.choices[cars.check.answer], "5", "the AI's wrong check (3) is replaced");
assert.strictEqual(cars.example.problem, "Does the machine need adjusting?");
// unusable numbers: the example is dropped rather than shown wrong
assert.strictEqual(cleanLesson({ title: "t", chunks: [chunk(), chunk(), chunk({ example: { problem: "x", calc: { type: "z-test-mean", sd: 0 } } })] },
  { number: 10, prevNumber: 9 }).chunks[2].example, null);
// gaps: a hand-worked z example is sent back; a missing example page is named
assert.ok(lessonGaps({ chunks: Array.from({ length: 7 }, () => chunk({ example: { problem: "p", steps: ["z = −3"], answer: "Reject H₀" } })) })
  .some((g) => /calc/.test(g)), "hand-worked z is sent back for calc");
assert.ok(lessonGaps({ chunks: Array.from({ length: 7 }, (_, i) => chunk({ hook: "h" + i, page: 3 + i, example: null })) }, { examplePages: [10, 13] })
  .some((g) => /page 13/.test(g)), "an uncovered example page is named");
console.log("calc lessons ok");

const { examplePageGroups } = require("../lib/lesson");
// made-up slides with the same shape as a real lesson: one story on pages 3 and 10, three different examples sharing a template
const slideText = require("fs").readFileSync(require("path").join(__dirname, "fixtures", "example-pages.txt"), "utf8");
assert.deepStrictEqual(examplePageGroups(slideText), [[3, 10], [11], [12], [13]], "the soda question (p.3) and its solution (p.10) are one example");
assert.ok(lessonGaps({ chunks: Array.from({ length: 7 }, (_, i) => chunk({ hook: "h" + i, page: i === 0 ? 10 : 20 + i })) }, { examplePages: [[3, 10]] })
  .every((g) => !/page/.test(g)), "covering either page of a group is enough");
console.log("example groups ok");

// the same worked example twice: the second copy loses its example, its marker and its z check
const soda = { type: "z-test-mean", claim: 12, xbar: 11.85, sd: 0.5, n: 100, alpha: 0.05, tail: "left" };
const twice = cleanLesson({ title: "t", chunks: [chunk({ example: { problem: "a", calc: soda } }), chunk({ title: "α", example: { problem: "b", calc: { ...soda } } }), chunk()] },
  { number: 10, prevNumber: 9 });
assert.ok(twice.chunks[0].computed && twice.chunks[0].example);
assert.strictEqual(twice.chunks[1].example, null);
assert.strictEqual(twice.chunks[1].computed, undefined);
assert.strictEqual(twice.chunks[1].diagram.mark, null, "the α chunk keeps the shaded curve without the sample marker");
console.log("dedupe ok");
