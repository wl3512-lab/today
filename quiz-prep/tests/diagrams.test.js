const assert = require("assert");
const path = require("path");
const dir = process.env.PUBLIC_DIR || "public";
const D = require(path.join(__dirname, "..", dir, "diagrams.js"));

const count = (s, re) => (s.match(re) || []).length;

// bell: every curve point stays inside the 230px-tall box
const left = D.bellSVG({ shade: "left", cut: 1.65, areaLabel: "α = 0.05" });
assert.ok(left.startsWith("<svg"), "bell is an svg");
const ys = [...left.matchAll(/[ML]\s?([\d.]+)[ ,]([\d.-]+)/g)].map((m) => Number(m[2]));
assert.ok(ys.length > 50 && ys.every((y) => y >= 0 && y <= 230), "bell path inside viewBox");
assert.strictEqual(count(left, /class="dg-tail"/g), 1);
assert.ok(left.includes("−1.65"), "cutoff labelled with a real minus");
assert.strictEqual(count(D.bellSVG({ shade: "both", cut: 2, areaLabel: "α = 0.05" }), /class="dg-tail"/g), 2);
assert.strictEqual(count(D.bellSVG({ shade: "middle", cut: 2, areaLabel: "95%" }), /class="dg-mid"/g), 1);
const marked = D.bellSVG({ shade: "left", cut: 1.65, areaLabel: "α", mark: -3, markLabel: "your z", mean: 12, se: 0.05 });
assert.ok(marked.includes('class="dg-mark"') && marked.includes("11.85"), "mark drawn and x value shown");
assert.strictEqual(D.bellSVG({ shade: "left", cut: 9 }), "", "cut out of range");
assert.strictEqual(D.bellSVG({ shade: "up", cut: 1 }), "", "bad shade");

// interval
const iv = D.intervalSVG({ center: 50, margin: 4, centerLabel: "x̄ = 50", mark: 52, markLabel: "μ₀ = 52" });
assert.ok(iv.includes("46") && iv.includes("54") && iv.includes('class="dg-param"'));
assert.strictEqual(D.intervalSVG({ center: 50, margin: 0 }), "");

// html ones
assert.strictEqual(count(D.flowHTML({ steps: ["State H₀", "Find z", "Decide"] }), /<li/g), 3);
const f = D.formulaHTML({ parts: [{ text: "z", label: "test statistic", role: "result" }, { text: "=", role: "op" }, { text: "x̄", label: "sample mean", role: "stat" }] });
assert.ok(f.includes("role-result") && f.includes("role-stat") && f.includes("sample mean"));
assert.strictEqual(count(D.compareHTML({ columns: [{ head: "H₀", items: ["μ = 12"] }, { head: "Hₐ", items: ["μ < 12", "μ > 12"] }] }), /<li/g), 3);

// escaping and dispatch
assert.ok(!D.flowHTML({ steps: ["<script>x</script>", "b"] }).includes("<script>"));
assert.strictEqual(D.diagram({ type: "pie" }), "");
assert.strictEqual(D.diagram(null), "");
assert.ok(D.diagram({ type: "bell", shade: "right", cut: 1.28, areaLabel: "α = 0.1" }).includes("1.28"));
assert.strictEqual(D.fmt(-1.6500), "−1.65");
assert.strictEqual(D.fmt(0.10000000000000002), "0.1");
const off = D.bellSVG({ shade: "right", cut: 2.33, areaLabel: "α = 0.01", mark: 5, markLabel: "your sample: z = 5" });
assert.ok(off.includes("off the chart") && off.includes('class="dg-mark"'), "z beyond 4 is drawn at the edge with a note");
console.log("diagrams ok");
