// Cleans the AI's New lesson JSON before it is saved. A diagram with numbers out of range becomes null
// (a wrong picture is worse than none), a check whose answer isn't one of its choices is dropped,
// and math is turned into plain text. Ranges match public/diagrams.js.
const { plainMath } = require("./text");
const { runCalc } = require("./calc");

const str = (s, max) => (typeof s === "string" || typeof s === "number" ? plainMath(String(s)).slice(0, max).trim() : "");
const toNum = (v) => (typeof v === "number" ? v : typeof v === "string" && v.trim() !== "" ? Number(v) : NaN);
const ok = (v) => Number.isFinite(v);
const ROLES = ["stat", "param", "spread", "size", "result", "op"];

function cleanDiagram(d) {
  if (!d || typeof d !== "object") return null;
  if (d.type === "bell") {
    const cut = toNum(d.cut), mark = toNum(d.mark), mean = toNum(d.mean), se = toNum(d.se);
    if (!["left", "right", "both", "middle"].includes(d.shade) || !ok(cut) || cut <= 0 || cut > 4) return null;
    const units = ok(mean) && ok(se) && se > 0;
    return { type: "bell", shade: d.shade, cut, areaLabel: str(d.areaLabel, 40),
      mark: ok(mark) && Math.abs(mark) <= 12 ? mark : null, markLabel: str(d.markLabel, 50) || null,
      mean: units ? mean : null, se: units ? se : null };
  }
  if (d.type === "interval") {
    const center = toNum(d.center), margin = toNum(d.margin), mark = toNum(d.mark);
    if (!ok(center) || !ok(margin) || margin <= 0) return null;
    return { type: "interval", center, margin, centerLabel: str(d.centerLabel, 40),
      mark: ok(mark) && Math.abs(mark - center) <= 4 * margin ? mark : null, markLabel: str(d.markLabel, 60) || null };
  }
  if (d.type === "flow") {
    const steps = (Array.isArray(d.steps) ? d.steps : []).map((s) => str(s, 80)).filter(Boolean).slice(0, 6);
    return steps.length >= 2 ? { type: "flow", steps } : null;
  }
  if (d.type === "formula") {
    const parts = (Array.isArray(d.parts) ? d.parts : []).map((p) => {
      const text = str(p?.text, 20), label = str(p?.label, 30) || null;
      return { text, label, role: ROLES.includes(p?.role) ? p.role : label ? "param" : "op" };
    }).filter((p) => p.text).slice(0, 16);
    return parts.length >= 2 ? { type: "formula", parts } : null;
  }
  if (d.type === "compare") {
    const columns = (Array.isArray(d.columns) ? d.columns : []).map((c) => ({
      head: str(c?.head, 40), items: (Array.isArray(c?.items) ? c.items : []).map((x) => str(x, 90)).filter(Boolean).slice(0, 5)
    })).filter((c) => c.head && c.items.length).slice(0, 3);
    return columns.length >= 2 ? { type: "compare", columns } : null;
  }
  return null;
}

function cleanCheck(c) {
  if (!c || typeof c !== "object") return null;
  const choices = (Array.isArray(c.choices) ? c.choices : []).map((x) => str(x, 160)).filter(Boolean);
  const answer = toNum(c.answer), q = str(c.q, 300);
  if (!q || choices.length < 2 || choices.length > 4 || !Number.isInteger(answer) || answer < 0 || answer >= choices.length) return null;
  return { q, choices, answer, why: str(c.why, 400) };
}

function cleanExample(e) {
  if (!e || typeof e !== "object") return null;
  const problem = str(e.problem, 400), steps = (Array.isArray(e.steps) ? e.steps : []).map((s) => str(s, 200)).filter(Boolean).slice(0, 6);
  return problem && steps.length ? { problem, steps, answer: str(e.answer, 200) } : null;
}

function cleanLesson(raw, { number, prevNumber }) {
  const seen = new Set();
  const chunks = (Array.isArray(raw?.chunks) ? raw.chunks : []).map((c) => {
    const page = toNum(c?.page), ex = c?.example;
    const out = { title: str(c?.title, 80), idea: str(c?.idea, 300), diagram: cleanDiagram(c?.diagram), example: cleanExample(ex),
      hook: str(c?.hook, 160), check: cleanCheck(c?.check), page: Number.isInteger(page) && page > 0 ? page : null };
    // Numbers off a slide: the app does the math, so its steps, answer, curve and check replace the AI's.
    if (ex && typeof ex === "object" && ex.calc) {
      const done = runCalc(ex.calc), key = done && JSON.stringify(done.steps);
      out.example = done && !seen.has(key) ? { problem: str(ex.problem, 400) || "Worked example", steps: done.steps, answer: done.answer } : null;
      if (done && !seen.has(key)) Object.assign(out, { diagram: cleanDiagram(done.diagram) || out.diagram, check: done.check, computed: true });
      // the AI sometimes hangs one example on two chunks: the repeat keeps just the shaded curve
      else if (done) out.diagram = out.diagram || cleanDiagram({ ...done.diagram, mark: null, markLabel: null, mean: null, se: null });
      if (key) seen.add(key);
    }
    return out;
  }).filter((c) => c.title && c.idea).slice(0, 8);
  if (chunks.length < 3) throw new Error("The AI's lesson came back too thin. Click Rebuild.");
  const r = raw.recap;
  const recap = prevNumber && r && str(r.rule, 240) ? {
    lesson: prevNumber, title: str(r.title, 80), rule: str(r.rule, 240), diagram: cleanDiagram(r.diagram),
    recall: (Array.isArray(r.recall) ? r.recall : []).map((x) => ({ q: str(x?.q, 200), a: str(x?.a, 240) })).filter((x) => x.q && x.a).slice(0, 3)
  } : null;
  return { title: str(raw.title, 80) || "Lesson " + number, recap, chunks };
}

// Sample hooks shown to the AI. They are from other subjects on purpose: given stats examples, it copied them verbatim.
const PROMPT_HOOKS = ["Spring forward, fall back.", "Never Eat Soggy Waffles (N, E, S, W).", "i before e, except after c."];

// What's still missing from a cleaned lesson, as sentences the AI can act on ([] = good enough).
// examplePages: slide pages with a worked example, each of which should become a chunk.
function lessonGaps(lesson, { examplePages = [], calc = true } = {}) {
  const chunks = lesson?.chunks || [], gaps = [];
  if (chunks.length < 7) gaps.push(`Only ${chunks.length} chunks: make 7-8, one per slide topic, covering every slide page.`);
  const drawn = chunks.filter((c) => c.diagram).length;
  if (drawn < 5) gaps.push(`Only ${drawn} chunks have a diagram: give at least 5 of them one.`);
  for (const c of chunks) {
    const e = c.example;
    if (!e || c.computed || !calc) continue;
    const text = e.problem + " " + e.steps.join(" ") + " " + e.answer;
    if (/H₀|Hₐ|σx̄|σp̂|reject|C\.I\.|±|√|\(\s*[−-]?[\d.]+\s*[−-]\s*[\d.]+\s*\)\s*\//i.test(text))
      gaps.push(`The example "${e.problem.slice(0, 40)}" in "${c.title}" is worked by hand: give it as {"calc": …} so the app computes it.`);
  }
  for (const group of examplePages.map((g) => [].concat(g))) if (!chunks.some((c) => group.includes(c.page) && c.example))
    gaps.push(`The worked example on page ${group.join("/")} is missing: give it its own chunk with "page": ${group[0]}${calc ? " and a calc example" : ""}.`);
  for (const c of chunks) if (PROMPT_HOOKS.includes(c.hook)) gaps.push(`The hook "${c.hook}" is copied from the instructions: write your own for "${c.title}".`);
  return gaps;
}

// Slide pages with a worked example, grouped when they tell the same story (a question on one page, its solution later).
// Only each page's opening and the words right after "Example" are compared: the fill-in template under every example is the same.
function examplePageGroups(text) {
  const parts = String(text || "").split(/\[page (\d+)\]/), pages = [];
  const words = (t) => t.toLowerCase().match(/[a-z]{2,}/g) || [];
  const shingles = (w) => new Set(w.slice(0, -5).map((_, i) => w.slice(i, i + 6).join(" ")));
  for (let i = 1; i < parts.length; i += 2) {
    const t = parts[i + 1] || "", at = t.search(/Example\b/i);
    if (at < 0) continue;
    pages.push({ n: Number(parts[i]), sh: new Set([...shingles(words(t).slice(0, 35)), ...shingles(words(t.slice(at)).slice(0, 35))]) });
  }
  const groups = [];
  for (const p of pages) {
    const same = groups.find((g) => [...p.sh].filter((x) => g[0].sh.has(x)).length >= 10);
    if (same) same.push(p); else groups.push([p]);
  }
  return groups.map((g) => g.map((p) => p.n));
}

module.exports = { cleanLesson, cleanDiagram, lessonGaps, examplePageGroups, PROMPT_HOOKS };
