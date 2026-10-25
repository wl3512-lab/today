// Worked examples the app computes itself. Every model on the class proxy got slide 13's toy cars wrong
// (z = 3, 2.5, 2.24 for a true z = 5), so the AI only copies the numbers off the slide and this does the math,
// writes the steps, makes the decision and draws the matching curve. Cutoffs are the course's own table (configure()).
let CUT = { one: { 0.1: 1.28, 0.05: 1.65, 0.01: 2.33 }, two: { 0.1: 1.65, 0.05: 2, 0.01: 2.58 } };
let LEVEL = { 90: 1.65, 95: 2, 99: 2.58 };
// a course whose professor uses another table (±1.96 …) sets it from its settings
function configure({ cutoffs, levels } = {}) { if (cutoffs) CUT = cutoffs; if (levels) LEVEL = levels; }

const r = (x) => Math.round(x * 1e4) / 1e4;
const f = (x) => { const v = r(x); return v === 0 ? "0" : (v < 0 ? "−" : "") + String(Math.abs(v)); };
const num = (v) => (typeof v === "number" ? v : typeof v === "string" && v.trim() !== "" ? Number(v) : NaN);
const pos = (v) => Number.isFinite(v) && v > 0;
// "σx̄ = σ/√n = 0.5/√100 = 0.5/10 = 0.05" (≈ when √n isn't whole)
const seMeanStep = (sd, n, se) => { const s = Math.sqrt(n), w = Number.isInteger(s);
  return `σx̄ = σ/√n = ${f(sd)}/√${n} ${w ? "=" : "≈"} ${f(sd)}/${f(s)} ${w ? "=" : "≈"} ${f(se)}`; };

// The "What is z?" style check: the right value plus the slips students actually make.
function numberCheck(q, right, slips, why) {
  const seen = new Map();
  for (const v of [right, ...slips]) if (Number.isFinite(v) && !seen.has(f(v))) seen.set(f(v), v);
  if (seen.size < 3) seen.set(f(right + 1), right + 1);
  const choices = [...seen.entries()].sort((a, b) => a[1] - b[1]).map(([s]) => s).slice(0, 4);
  if (!choices.includes(f(right))) choices[choices.length - 1] = f(right);
  return { q, choices, answer: choices.indexOf(f(right)), why };
}

function zTest(c, kind) {
  const tail = c.tail, alpha = num(c.alpha), claim = num(c.claim), n = num(c.n);
  const cut = CUT[tail === "two" ? "two" : "one"]?.[alpha];
  if (!["left", "right", "two"].includes(tail) || !cut || !Number.isInteger(n) || n < 1 || !Number.isFinite(claim)) return null;
  let stat, se, steps = [], slips;
  const sym = { left: "<", right: ">", two: "≠" }[tail], tailName = { left: "left-tailed", right: "right-tailed", two: "two-tailed" }[tail];
  if (kind === "mean") {
    const xbar = num(c.xbar), sd = num(c.sd);
    if (!Number.isFinite(xbar) || !pos(sd)) return null;
    stat = xbar; se = sd / Math.sqrt(n);
    steps.push(`H₀: μ = ${f(claim)}  ·  Hₐ: μ ${sym} ${f(claim)}  ·  ${tailName} test`);
    steps.push(seMeanStep(sd, n, se));
    slips = [-(xbar - claim) / se, (xbar - claim) / sd, (xbar - claim) / (sd / n)];
  } else {
    const p = c.count != null ? num(c.count) / n : num(c.phat);
    if (!(claim > 0 && claim < 1) || !(p >= 0 && p <= 1)) return null;
    stat = p; se = Math.sqrt(claim * (1 - claim) / n);
    if (c.count != null) steps.push(`p̂ = x/n = ${f(num(c.count))}/${n} = ${f(p)}`);
    steps.push(`H₀: p = ${f(claim)}  ·  Hₐ: p ${sym} ${f(claim)}  ·  ${tailName} test`);
    steps.push(`σp̂ = √(p(1 − p)/n) = √(${f(claim)} × ${f(1 - claim)}/${n}) = ${f(se)}`);
    slips = [-(p - claim) / se, (p - claim) / (claim * (1 - claim) / n), (p - claim) / Math.sqrt(claim * (1 - claim))];
  }
  const z = r((stat - claim) / se), sym2 = kind === "mean" ? "x̄ − μ₀" : "p̂ − p", seName = kind === "mean" ? "σx̄" : "σp̂";
  steps.push(`z = (${sym2})/${seName} = (${f(stat)} − ${f(claim)})/${f(se)} = ${f(stat - claim)}/${f(se)} = ${f(z)}`);
  const cutText = tail === "two" ? "±" + f(cut) : tail === "left" ? f(-cut) : f(cut);
  steps.push(`Critical value (α = ${f(alpha)}, ${tailName}): z = ${cutText}`);
  const reject = tail === "left" ? z < -cut : tail === "right" ? z > cut : Math.abs(z) > cut;
  steps.push(reject ? `z = ${f(z)} is past ${cutText}: it lands in the rejection region.` : `z = ${f(z)} is not past ${cutText}: it lands outside the rejection region.`);
  const meaning = String((reject ? c.ifReject : c.ifFail) || "").trim();
  return {
    kind: "test", z, reject, se: r(se), steps,
    answer: (reject ? "Reject H₀." : "Fail to reject H₀.") + (meaning ? " " + meaning : ""),
    diagram: { type: "bell", shade: tail === "two" ? "both" : tail, cut, areaLabel: tail === "two" ? `α/2 = ${f(alpha / 2)}` : `α = ${f(alpha)}`,
      mark: z, markLabel: `your sample: z = ${f(z)}`, mean: claim, se: r(se) },
    check: numberCheck("What is the test statistic z?", z, slips, `${seName} = ${f(se)}, so z = (${f(stat)} − ${f(claim)})/${f(se)} = ${f(z)}. Dividing by σ instead of the standard error is the usual slip.`)
  };
}

function ci(c, kind) {
  const level = num(c.level), zc = LEVEL[level], n = num(c.n);
  if (!zc || !Number.isInteger(n) || n < 1) return null;
  let center, se, steps = [`Confidence level ${level}% → z = ${f(zc)}`], label;
  if (kind === "mean") {
    const xbar = num(c.xbar), sd = num(c.sd);
    if (!Number.isFinite(xbar) || !pos(sd)) return null;
    center = xbar; se = sd / Math.sqrt(n); label = `x̄ = ${f(xbar)}`;
    steps.push(seMeanStep(sd, n, se));
  } else {
    const p = c.count != null ? num(c.count) / n : num(c.phat);
    if (!(p > 0 && p < 1)) return null;
    if (c.count != null) steps.push(`p̂ = x/n = ${f(num(c.count))}/${n} = ${f(p)}`);
    center = p; se = Math.sqrt(p * (1 - p) / n); label = `p̂ = ${f(p)}`;
    steps.push(`σp̂ = √(p̂(1 − p̂)/n) = √(${f(p)} × ${f(1 - p)}/${n}) = ${f(se)}`);
  }
  const E = r(zc * se), lo = r(center - E), hi = r(center + E);
  steps.push(`E = z × ${kind === "mean" ? "σx̄" : "σp̂"} = ${f(zc)} × ${f(se)} = ${f(E)}`);
  steps.push(`C.I. = ${kind === "mean" ? "x̄" : "p̂"} ± E = ${f(center)} ± ${f(E)} = (${f(lo)}, ${f(hi)})`);
  const mark = num(c.mark);
  return {
    kind: "ci", E, lo, hi, se: r(se), steps,
    answer: `(${f(lo)}, ${f(hi)}). We are ${level}% confident the true ${kind === "mean" ? "mean μ" : "proportion p"} is in this interval.`,
    diagram: { type: "interval", center, margin: E, centerLabel: label,
      mark: Number.isFinite(mark) ? mark : null, markLabel: Number.isFinite(mark) ? String(c.markLabel || f(mark)) : null },
    check: numberCheck("What is the margin of error E?", E, [zc * (kind === "mean" ? num(c.sd) : Math.sqrt(center * (1 - center))), se, 2 * E],
      `E = z × standard error = ${f(zc)} × ${f(se)} = ${f(E)}. Forgetting to divide by √n is the usual slip.`)
  };
}

function size(c, kind) {
  const level = num(c.level), zc = LEVEL[level], E = num(c.E);
  if (!zc || !pos(E)) return null;
  if (kind === "mean") {
    const sd = num(c.sd);
    if (!pos(sd)) return null;
    const raw = (zc * sd / E) ** 2, n = Math.ceil(r(raw));
    return { kind: "size", n, steps: [`Confidence level ${level}% → z = ${f(zc)}`, `n = (zσ/E)² = (${f(zc)} × ${f(sd)}/${f(E)})² = ${f(zc * sd / E)}² = ${f(raw)}`,
      Number.isInteger(r(raw)) ? `n = ${n}` : `Round UP: n = ${n}`], answer: `n = ${n}`, diagram: null,
      check: numberCheck("How big must the sample be?", n, [Math.ceil(zc * sd / E), Math.ceil((sd / E) ** 2)], `n = (zσ/E)² = ${f(raw)}${Number.isInteger(r(raw)) ? "" : ", rounded up"}. Forgetting to square is the usual slip.`) };
  }
  const p = c.p != null ? num(c.p) : 0.5;
  if (!(p > 0 && p < 1)) return null;
  const raw = zc * zc * p * (1 - p) / (E * E), n = Math.ceil(r(raw));
  return { kind: "size", n, steps: [`Confidence level ${level}% → z = ${f(zc)}`, `n = z² p(1 − p)/E² = ${f(zc)}² × ${f(p)} × ${f(1 - p)}/${f(E)}² = ${f(raw)}`,
    Number.isInteger(r(raw)) ? `n = ${n}` : `Round UP: n = ${n}`], answer: `n = ${n}`, diagram: null,
    check: numberCheck("How big must the sample be?", n, [Math.ceil(zc * Math.sqrt(p * (1 - p)) / E), Math.ceil(p * (1 - p) / (E * E))], `n = z² p(1 − p)/E² = ${f(raw)}${Number.isInteger(r(raw)) ? "" : ", rounded up"}.`) };
}

function runCalc(c) {
  if (!c || typeof c !== "object") return null;
  const go = { "z-test-mean": () => zTest(c, "mean"), "z-test-prop": () => zTest(c, "prop"), "ci-mean": () => ci(c, "mean"),
    "ci-prop": () => ci(c, "prop"), "size-mean": () => size(c, "mean"), "size-prop": () => size(c, "prop") }[c.type];
  return go ? go() : null;
}

module.exports = { runCalc, configure, get CUT() { return CUT; }, get LEVEL() { return LEVEL; } };
