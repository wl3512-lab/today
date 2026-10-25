// Quiz Prep local server. This is the only file that reads .env.
require("dotenv").config();
const express = require("express");
const path = require("path");

const app = express();
const PORT = process.env.PORT || 3123;

app.use(express.json({ limit: "40mb" }));
// One line per page load and print request in ~/.quiz-prep.log, to see where printing stops.
app.use((req, res, next) => {
  if (/^\/(app\.js|api\/print|print\/)/.test(req.path)) {
    const ua = req.get("user-agent") || "";
    console.log(new Date().toLocaleTimeString(), req.method, req.path, /Chrome\//.test(ua) ? "chrome" : /AppleWebKit/.test(ua) ? "today-webview" : "other");
  }
  next();
});
app.use(express.static(path.join(__dirname, process.env.PUBLIC_DIR || "public")));
app.use("/photos", express.static(path.join(__dirname, "data", "photos")));
const fs = require("fs");
const { loadProfile, courseSettings, courseLine, niceNumbers, courseCutoffs, lmsName } = require("./lib/profile");
const PROFILE = loadProfile();
// which of her quiz courses this Quiz Prep serves (profile.quizPrep.courses), and how that course works
const COURSE_KEY = process.env.COURSE_KEY || (PROFILE.quizPrep.courses || [])[0] || "course";
const COURSE = courseSettings(PROFILE, COURSE_KEY);
const STATS = COURSE.subject === "stats";   // z-test calculator, number banks, cutoff tables
require("./lib/calc").configure({ cutoffs: COURSE.cutoffs, levels: COURSE.levels });
const { markedParts, focusPlan, mixOff } = require("./lib/marks");
const { plainMath, sameAnswer } = require("./lib/text");
const { askClaude, claudeBin } = require("./lib/claude");

// Photos already saved in data/photos, so you can pick them without the file dialog.
app.get("/api/photos", (req, res) => {
  const dir = path.join(__dirname, "data", "photos");
  const files = fs.readdirSync(dir).filter((f) => /\.(jpe?g|png)$/i.test(f)).sort();
  res.json(files);
});

// Printing. Today shows this app inside a web view that ignores window.print(),
// so there the page posts the paper here and opens /print/:id in her real browser.
const printJobs = new Map();
app.post("/api/print", (req, res) => {
  const { id, html, title } = req.body || {};
  if (!/^[a-z0-9]{8,40}$/i.test(String(id)) || typeof html !== "string") return res.status(400).json({ error: "Nothing to print." });
  printJobs.set(id, { html, title: String(title || "Print") });
  if (printJobs.size > 20) printJobs.delete(printJobs.keys().next().value);
  res.json({ ok: true });
});
app.get("/print/:id", async (req, res) => {
  // the browser can ask before the page's post lands, so give it a moment
  for (let i = 0; i < 20 && !printJobs.has(req.params.id); i++) await new Promise((r) => setTimeout(r, 150));
  const job = printJobs.get(req.params.id);
  if (!job) return res.status(404).send("That print expired. Go back to Quiz Prep and click Print again.");
  const title = job.title.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  res.send(`<!doctype html><html lang="en"><head><meta charset="utf-8"><title>${title}</title>
<link rel="stylesheet" href="/style.css">
<style>:root { color-scheme: light; } body { background: #fff; color: #111827; } main { max-width: 760px; margin: 0 auto; padding: 24px 16px; }
.paper { border: 0; box-shadow: none; } @media print { main { padding: 0; } .paper { padding: 0; } }</style></head>
<body><main>${job.html}</main><script>addEventListener("load", () => setTimeout(print, 300));</script></body></html>`);
});

// Tells the page whether the server is set up, without ever showing the token.
app.get("/api/health", (req, res) => {
  res.set("Access-Control-Allow-Origin", "*"); // Today checks this from its own window
  res.json({
    ok: true,
    course: { key: COURSE.key, label: COURSE.label, paperLabel: COURSE.paperLabel },
    baseUrlLoaded: Boolean(process.env.AI_BASE_URL || claudeBin()),
    tokenLoaded: Boolean(process.env.AI_TOKEN)
  });
});

// ── AI helper: the class AI proxy in AI_BASE_URL, else the student's own Claude Code (lib/claude.js) ──
async function askAI({ prompt, images = [], model = "openai/gpt-4o", maxTokens = 3000 }) {
  if (!process.env.AI_BASE_URL) return askClaude({ prompt, images });
  const headers = { "Content-Type": "application/json" };
  if (process.env.AI_TOKEN) headers.Authorization = "Bearer " + process.env.AI_TOKEN;
  const input = { prompt, max_completion_tokens: maxTokens, temperature: 0.2 };
  if (images.length) input.image_input = images;
  const r = await fetch(process.env.AI_BASE_URL, { method: "POST", headers, body: JSON.stringify({ model, input }) });
  const text = await r.text();
  let d; try { d = JSON.parse(text); } catch { throw new Error("The AI service sent back something unreadable."); }
  if (!r.ok || d.error) throw new Error("AI service error: " + (d.error || r.status));
  return Array.isArray(d.output) ? d.output.join("") : String(d.output || "");
}

// Quizzes taken WITHOUT a calculator: the professor picks numbers that work by hand (lib/profile.js, per course).
const NICE_NUMBERS = niceNumbers(COURSE);

// Finds numbers a student couldn't get by hand. Returns a list of problems ([] = clean).
const TABLE = new Set(["0.6826","0.9544","0.9974","0.1587","0.8413","0.0228","0.9772","0.0013","0.9987","0.0668","0.9332","0.3085","0.6915","0.0062","0.9938","0.4772","0.3413","0.4987","0.8664","0.9876","0.3830","0.4332"]);
function messyNumbers(text) {
  const t = String(text), issues = [];
  for (const m of t.matchAll(/-?\d*\.\d+/g)) {
    const raw = m[0].replace(/^-/, ""), dec = raw.split(".")[1];
    if (dec.length >= 4 && !TABLE.has(raw.startsWith(".") ? "0" + raw : raw)) issues.push("needs a calculator: " + m[0]);
  }
  for (const m of t.matchAll(/z\s*[=≈](?:[^,;=\n"]*?[=≈])?\s*(-?\d+(?:\.\d+)?)(?![\d.]*\s*[\/)])/gi)) {
    const z = Math.abs(Number(m[1]));
    if (Math.abs(z * 2 - Math.round(z * 2)) > 1e-9) issues.push("z is not a whole number or half: " + m[0]);
  }
  for (const m of t.matchAll(/sqrt\(\s*(\d+)\s*\)|√\s*(\d+)\b/g)) {
    const n = Number(m[1] || m[2]);
    if (n > 1 && !Number.isInteger(Math.sqrt(n))) issues.push("√" + n + " is not whole");
  }
  for (const m of t.matchAll(/(\d+(?:\.\d+)?)\s*\/\s*(\d+(?:\.\d+)?)\s*=\s*(-?\d+(?:\.\d+)?)/g)) {
    const q = Number(m[1]) / Number(m[2]);
    if (Math.abs(q - Number(m[3])) > 1e-9 && Math.round(q * 1000) / 1000 !== q) issues.push("rounded division: " + m[0]);
  }
  return [...new Set(issues)];
}


// Clean number sets made in code, so every answer works by hand. The AI writes
// the story around them; it never picks the numbers.
const PHI = { "0.5": 0.6915, "1": 0.8413, "1.5": 0.9332, "2": 0.9772, "2.5": 0.9938, "3": 0.9987 };
const pick = (a) => a[Math.floor(Math.random() * a.length)];
const r4 = (x) => Math.round(x * 10000) / 10000;
function numberBank(count = 10) {
  const out = [];
  for (let i = 0; i < count; i++) {
    if (i % 2 === 0) {
      const n = pick([16, 25, 36, 49, 64, 81, 100, 144, 225, 400]), root = Math.sqrt(n);
      const se = pick([0.5, 0.75, 1, 1.5, 2, 2.5, 3, 4, 5]), sigma = se * root;
      if (!Number.isInteger(sigma) && sigma * 10 % 1) { i--; continue; }
      const mu = 5 * Math.round((40 + Math.random() * 300) / 5), z = pick([1, 1, 2, 2, 3, 1.5]);
      const lo = r4(mu - z * se), hi = r4(mu + z * se), tail = r4(1 - PHI[z]);
      out.push({ kind: "mean", mu, sigma, n, sqrt_n: root, se, z, value_below: lo, value_above: hi,
        P_below: tail, P_above: tail, P_between: r4(2 * PHI[z] - 1), P_above_low_value: r4(PHI[z]),
        n_ge_30: n >= 30 });
    } else {
      const [p, num] = pick([[0.1, 0.3], [0.9, 0.3], [0.2, 0.4], [0.8, 0.4], [0.5, 0.5]]);
      const n = pick([100, 144, 225, 256, 400, 625, 900].filter((m) => m * Math.min(p, 1 - p) >= 10));
      const se = num / Math.sqrt(n);
      if (r4(se) !== se || String(se).split(".")[1]?.length > 4) { i--; continue; }
      const z = pick([1, 2, 2, 3, 1.5]), hi = r4(p + z * se), lo = r4(p - z * se);
      out.push({ kind: "proportion", p, n, np: r4(n * p), n_1_minus_p: r4(n * (1 - p)), p_times_1_minus_p: r4(p * (1 - p)),
        se, z, phat_above: hi, phat_below: lo, count_above: Number.isInteger(hi * n) ? hi * n : null,
        count_below: Number.isInteger(lo * n) ? lo * n : null, P_tail: r4(1 - PHI[z]), P_between: r4(2 * PHI[z] - 1) });
    }
  }
  return out;
}

function pullJSON(text) {
  const a = text.indexOf("{"), b = text.lastIndexOf("}");
  if (a < 0 || b < a) throw new Error("The AI didn't return a quiz. Try again.");
  return JSON.parse(text.slice(a, b + 1));
}

const EXTRACT_PROMPT = `You are reading photos of one printed quiz (one photo per page, in order).
Transcribe it into JSON ONLY, no other text, with this shape:
{"format":{"title":string,"instructions":string,"calculatorAllowed":boolean|null,"showWork":boolean},
 "difficulty":"easy"|"medium"|"hard",
 "topics":string,
 "questions":[{"number":int,"type":"multiple_choice"|"short_answer"|"show_work","points":number,
   "text":string,"choices":[string],"parts":[{"label":string,"points":number,"text":string}]}]}
Rules: copy question text exactly; use ^ for exponents (36^2) and a/b for fractions.
"choices" holds lettered options like "A) 12" (empty array if none). Ignore handwriting, names, IDs and marked answers.
"parts" holds sub-questions like (a),(b),(c) or (i),(ii) with their own points (empty array if none).
A question with parts asking to compute or explain is "show_work". "topics" is a short comma list of what the questions test.`;

app.post("/api/extract", async (req, res) => {
  const photos = (req.body.photos || []).filter((p) => /^data:image\/(png|jpeg);base64,/.test(p.dataUrl || ""));
  if (!photos.length) return res.status(400).json({ error: "Choose at least one JPG or PNG photo first." });
  try {
    const raw = await askAI({ prompt: EXTRACT_PROMPT, images: photos.map((p) => p.dataUrl) });
    const q = pullJSON(raw);
    q.questions = (q.questions || []).map((x, i) => ({
      number: x.number || i + 1, type: x.type || "short_answer", points: Number(x.points) || 0,
      text: x.text || "", choices: x.choices || [], parts: x.parts || []
    }));
    q.length = q.questions.length;
    q.totalPoints = q.questions.reduce((s, x) => s + x.points, 0);
    q.sourcePhotos = photos.map((p) => p.name);
    res.json(q);
  } catch (err) {
    res.status(502).json({ error: err.message });
  }
});

app.post("/api/profiles", (req, res) => {
  const p = req.body || {};
  if (!Array.isArray(p.questions) || !p.questions.length) return res.status(400).json({ error: "The profile has no questions." });
  const slug = String(p.format?.title || "quiz").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "quiz";
  p.id = slug + "-" + new Date().toISOString().slice(0, 10);
  p.length = p.questions.length;
  p.totalPoints = p.questions.reduce((s, x) => s + (Number(x.points) || 0), 0);
  const file = path.join(__dirname, "data", "profiles", p.id + ".json");
  fs.writeFileSync(file, JSON.stringify(p, null, 2));
  res.json({ saved: "data/profiles/" + p.id + ".json", id: p.id });
});

app.get("/api/profiles", (req, res) => {
  const dir = path.join(__dirname, "data", "profiles");
  res.json(fs.readdirSync(dir).filter((f) => f.endsWith(".json")).map((f) => JSON.parse(fs.readFileSync(path.join(dir, f)))));
});

// ── Lesson slides (text pulled from PDFs in the browser) ──
const SLIDES_DIR = path.join(__dirname, "data", "slides");
app.post("/api/slides", (req, res) => {
  const { name, text } = req.body || {};
  if (!name || !String(text || "").trim()) return res.status(400).json({ error: "That PDF had no readable text." });
  const safe = String(name).replace(/\.pdf$/i, "").replace(/[^a-z0-9 _.-]/gi, "").trim() || "slides";
  fs.writeFileSync(path.join(SLIDES_DIR, safe + ".txt"), text);
  res.json({ saved: safe });
});
app.get("/api/slides", (req, res) => {
  res.json(fs.readdirSync(SLIDES_DIR).filter((f) => f.endsWith(".txt")).map((f) => ({
    name: f.replace(/\.txt$/, ""), chars: fs.statSync(path.join(SLIDES_DIR, f)).size })));
});
function slideText(names) {
  return (names || []).map((n) => {
    const f = path.join(SLIDES_DIR, String(n).replace(/[\/]/g, "") + ".txt");
    return fs.existsSync(f) ? "=== " + n + " ===\n" + fs.readFileSync(f, "utf8") : "";
  }).join("\n").slice(0, 24000);
}

// ── Step 7: generate a practice quiz that copies a profile's format ──
function shapeOf(profile) {
  return profile.questions.map((q) => ({
    number: q.number, type: q.type, points: q.points,
    choiceCount: q.choices.length,
    parts: q.parts.map((p) => ({ label: p.label, points: p.points, hasChoices: /\bA\)/.test(p.text) }))
  }));
}

function matchesShape(quiz, shape) {
  if (!Array.isArray(quiz.questions) || quiz.questions.length !== shape.length) return "wrong number of questions";
  for (let i = 0; i < shape.length; i++) {
    const q = quiz.questions[i], s = shape[i];
    if (q.type !== s.type) return "question " + (i + 1) + " has the wrong type";
    if (Number(q.points) !== s.points) return "question " + (i + 1) + " has the wrong points";
    if ((q.choices || []).length !== s.choiceCount) return "question " + (i + 1) + " needs " + s.choiceCount + " choices";
    if ((q.parts || []).length !== s.parts.length) return "question " + (i + 1) + " needs " + s.parts.length + " parts";
  }
  return null;
}

app.post("/api/practice", async (req, res) => {
  const { profileId, topics, slides } = req.body || {};
  let notes = slideText(slides);
  if (!notes && Array.isArray(req.body.lessons)) {
    for (const m of findMaterials().filter((m) => m.kind === "slides" && req.body.lessons.includes(m.number)))
      notes += "\n=== " + m.name + " ===\n" + (await pdfText(m.file));
    notes = notes.slice(0, 24000);
  }
  const file = path.join(__dirname, "data", "profiles", String(profileId || "").replace(/[^a-z0-9-]/gi, "") + ".json");
  if (!fs.existsSync(file)) return res.status(404).json({ error: "Choose a saved quiz profile first." });
  if (!String(topics || "").trim()) return res.status(400).json({ error: "Type the topics for this quiz first." });
  const profile = JSON.parse(fs.readFileSync(file));
  const shape = shapeOf(profile);
  const prompt = `Write a NEW practice quiz for ${COURSE.practiceIntro}.
Topics to test: ${topics}
Difficulty: ${profile.difficulty}.\n${NICE_NUMBERS}
It must copy this exact format, question by question (type, points, number of lettered choices, sub-parts with their labels and points):
${JSON.stringify(shape)}
${notes ? "Lecture slides for these lessons. Use ONLY their methods, formulas, notation and decision rules:\n" + notes + "\n" : ""}${STATS && /sampling|central limit|standard error|proportion|mean/i.test(topics) ? "USE ONLY THESE NUMBER SETS for anything numeric (copy exactly; every answer you need is in the set):\n" + JSON.stringify(numberBank(6)) + "\n" : ""}Here is the original quiz, for style and wording only. Do NOT reuse its topics or numbers:
${JSON.stringify(profile.questions)}
Rules:
- multiple_choice: exactly choiceCount choices written "A) ...", and the last one is "None of these" if the original had it.
- A part with hasChoices true puts its options inside its text as "A) ... B) ... C) ..." like the original.
- show_work parts must include real calculations with given numbers (like the original's tree diagram and probabilities), building on each other; at most one part may be a short interpretation.
- Only use methods an intro course teaches for these topics. Do not use chi-square, t-tests or ANOVA unless the topics name them.
- Each multiple-choice question has exactly ONE correct choice; make the others clearly wrong.
- Every question gets an answer key: the correct letter or value plus a short worked solution in "why".
- "why" is the steps a student would write, 1-3 short lines: formula, numbers plugged in, result, in the slides' notation (e.g. "σx̄ = σ/√n = 48/√144 = 48/12 = 4"). For multiple choice, also name the trap behind the most tempting wrong choice if there is one (e.g. "48 is σ itself, not σx̄").
Return JSON ONLY:
{"title":string,"instructions":string,"questions":[{"number":int,"type":string,"points":number,"text":string,"choices":[string],
 "parts":[{"label":string,"points":number,"text":string,"answer":string,"why":string}],"answer":string,"why":string}]}
Put the answer and why for a question with parts inside each part; for a question without parts use "answer" and "why".`;
  let quiz, problem = null;
  try {
    for (let attempt = 0; attempt < 3; attempt++) {
      const raw = await askAI({ prompt: problem ? prompt + "\nYour last try was rejected because " + problem + ". Fix it." : prompt, maxTokens: 4000, model: "openai/gpt-4o" });
      quiz = pullJSON(raw);
      quiz.questions = (quiz.questions || []).map((q) => ({ ...q, points: Number(q.points), choices: q.choices || [], parts: q.parts || [] }));
      problem = matchesShape(quiz, shape);
      if (!problem) {
        const messy = messyNumbers(JSON.stringify(quiz.questions));
        if (messy.length && attempt < 1) { problem = "it needs a calculator (" + messy.slice(0, 3).join("; ") + ")"; continue; }
        quiz.messy = messy;
        problem = null;
        break;
      }
    }
  } catch (err) {
    return res.status(502).json({ error: err.message });
  }
  if (problem) return res.status(502).json({ error: "The AI kept getting the format wrong (" + problem + "). Click Generate again." });
  // (nice-number check runs inside the checker prompt below)
  // ── Answer checker: solve again from scratch and compare ──
  try {
    const items = [];
    quiz.questions.forEach((q, qi) => {
      if (q.parts.length) q.parts.forEach((p, pi) => items.push({ key: qi + "." + pi, stem: q.text, question: p.text, given: p.answer }));
      else items.push({ key: String(qi), stem: "", question: q.text + (q.choices.length ? "\n" + q.choices.join("\n") : ""), given: q.answer });
    });
    const checkPrompt = `You are checking a practice quiz's answer key. For EACH item, solve it yourself from scratch, step by step, BEFORE looking at the given answer.
Then decide if the given answer is correct. For multiple choice, also check that exactly one choice is correct.\nAlso set agrees=false if the item needs a calculator: a sqrt that is not exact, a z-score that is not a whole number or half, or an answer that had to be rounded. Say so in "note".
${notes ? "Course slides (use their conventions):\n" + notes.slice(0, 12000) + "\n" : ""}Items:
${JSON.stringify(items.map(({ key, stem, question }) => ({ key, stem, question })))}
Given answers:
${JSON.stringify(items.map(({ key, given }) => ({ key, given })))}
Return JSON ONLY: {"checks":[{"key":string,"work":string,"yourAnswer":string,"agrees":boolean,"note":string}]}
"note" explains any problem in one sentence (empty if fine).`;
    const checked = pullJSON(await askAI({ prompt: checkPrompt, maxTokens: 4000, model: "openai/gpt-4o" }));
    for (const c of checked.checks || []) {
      const [qi, pi] = String(c.key).split(".").map(Number);
      const target = Number.isInteger(pi) ? quiz.questions[qi]?.parts[pi] : quiz.questions[qi];
      if (!target) continue;
      // the checker solved it from scratch, so its work explains an answer the writer left bare
      if (c.agrees) { if (!String(target.why || "").trim() && c.work) target.why = c.work; continue; }
      target.flag = "Checker got: " + (c.yourAnswer || "?") + (c.note ? ". " + c.note : "");
    }
    quiz.checked = true;
  } catch (err) {
    quiz.checked = false;
  }

  quiz.slides = slides || [];
  quiz.id = "practice-" + new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
  quiz.profileId = profile.id;
  quiz.topics = topics;
  quiz.totalPoints = quiz.questions.reduce((s, q) => s + q.points, 0);
  fs.writeFileSync(path.join(__dirname, "data", "practice", quiz.id + ".json"), JSON.stringify(quiz, null, 2));
  res.json(quiz);
});

// ── Study kit: everything for the next quiz, rebuilt each week ──
const os = require("os");
const MATERIALS_DIRS = (process.env.MATERIALS_DIRS || path.join(os.homedir(), "Downloads")).split(":");
const KITS_DIR = path.join(__dirname, "data", "kits");

async function pdfText(file) {
  const cache = path.join(SLIDES_DIR, path.basename(file).replace(/\.pdf$/i, "") + ".txt");
  if (fs.existsSync(cache) && fs.statSync(cache).mtimeMs >= fs.statSync(file).mtimeMs) return fs.readFileSync(cache, "utf8");
  const { getDocument } = await import("pdfjs-dist/legacy/build/pdf.mjs");
  const pdf = await getDocument({ data: new Uint8Array(fs.readFileSync(file)), useSystemFonts: true, verbosity: 0 }).promise;
  let t = "";
  for (let i = 1; i <= pdf.numPages; i++) {
    const c = await (await pdf.getPage(i)).getTextContent();
    t += "\n[page " + i + "] " + c.items.map((x) => x.str + (x.hasEOL ? "\n" : " ")).join("");
  }
  fs.writeFileSync(cache, t);
  return t;
}

// Finds the course's lesson slides and worksheets in Downloads (newest copy of each, " (1)" duplicates ignored).
// Which files count comes from the course settings: fileTag (a course code in the file name) and lessonWord ("Lesson").
function findMaterials() {
  const seen = new Map();
  for (const dir of MATERIALS_DIRS) {
    let files = [];
    try { files = fs.readdirSync(dir); } catch { continue; }
    for (const f of files) {
      if (!/\.pdf$/i.test(f) || !COURSE.fileFilter.test(f)) continue;
      const lesson = f.match(COURSE.filePattern), ws = f.match(/WS\s*#?\s*(\d+)|Worksheet\s*(\d+)/i);
      if (!lesson && !ws) continue;
      const key = f.replace(/\s*\(\d+\)(?=\.pdf$)/i, "").toLowerCase();
      const full = path.join(dir, f), m = fs.statSync(full).mtimeMs;
      if (!seen.has(key) || seen.get(key).mtime < m) seen.set(key, {
        name: f.replace(/\s*\(\d+\)(?=\.pdf$)/i, "").replace(/\.pdf$/i, ""), file: full, mtime: m,
        kind: lesson ? "slides" : "worksheet", number: Number(lesson ? lesson[1] : (ws[1] || ws[2])) });
    }
  }
  return [...seen.values()].sort((a, b) => a.kind.localeCompare(b.kind) || a.number - b.number || a.name.localeCompare(b.name));
}

// The professor announces each quiz's real topics on a slide ("Quiz#6 ... Topics included are ...").
// That beats the schedule sheet, so look for it in the newest slides first.
app.get("/api/announced", async (req, res) => res.json(await announced(Number(req.query.n))));
async function announced(n) {
  if (!n) return null;
  const slides = findMaterials().filter((m) => m.kind === "slides").sort((a, b) => b.number - a.number || b.mtime - a.mtime);
  for (const m of slides.slice(0, 4)) {
    let t = "";
    try { t = (await pdfText(m.file)).replace(/\s+/g, " "); } catch { continue; }
    const re = new RegExp("Quiz\\s*#?\\s*" + n + "\\b(.{0,600}?)Topics? included (?:are|is) (.+?)(?:\\[page|Exam|Quiz\\s*#|HW\\s*#|$)", "i");
    const hit = t.match(re);
    if (!hit) continue;
    const topics = hit[2].replace(/[❖➢•]/g, "").trim().replace(/\s*\.$/, "");
    const when = (hit[1].match(/(Monday|Tuesday|Wednesday|Thursday|Friday)\s*\d+\/\d+/i) || [])[0] || "";
    // which lessons' slides match those topics, by lesson title
    const low = topics.toLowerCase();
    const lessons = [...new Set(slides.filter((s) => {
      const title = s.name.replace(/^.*Lesson\s*\d+\s*-\s*/i, "").replace(/\s*Part\s+[IVX]+.*$|\s*Annotated.*$/i, "").toLowerCase().trim();
      return title && (low.includes(title) || title.split(/\s+/).filter((w) => w.length > 4).every((w) => low.includes(w.replace(/s$/, ""))));
    }).map((s) => s.number))].sort((a, b) => a - b);
    return { topics, when, lessons, source: m.name };
  }
  return null;
}

// ── For Today's study OS: the next quiz as a brief (gist, steps, watch-outs) ──
// Today swaps this in for its own brief so the Study page, nook card and
// "Right now" step all follow Quiz Prep's plan and the professor's topics.
app.get("/api/today", async (req, res) => {
  res.set("Access-Control-Allow-Origin", "*");
  const title = String(req.query.quiz || ""), n = Number((title.match(/Quiz\s*(\d+)/i) || [])[1]);
  const ann = await announced(n).catch(() => null);
  const kf = kitFile(title), kit = fs.existsSync(kf) ? JSON.parse(fs.readFileSync(kf)) : null;
  const prog = readProgress()[title] || {};
  const lessons = ann?.lessons?.length ? ann.lessons : [];
  const slides = findMaterials().filter((m) => m.kind === "slides" && lessons.includes(m.number)).map((m) => m.name);
  const known = (prog.known || []).length, cards = kit?.cards?.length || 0;
  const marks = Object.values(prog.marks || {}), right = marks.filter((m) => m === "right").length;
  const steps = [
    { id: "review", name: "Quiz Prep: read the Review, say each recipe out loud", minutes: 20, how: "Study kit → Review. Then Symbols & formulas: cover the table and write them from memory." },
    { id: "cards1", name: "Quiz Prep: flashcards until all are known", minutes: 15, how: "Study kit → Flashcards. Space flips, ✓ I know this, then 'Only cards I don't know'." },
    { id: "ws1", name: "Quiz Prep: fresh worksheet by hand, mark ✓/✗", minutes: 40, how: "Study kit → Worksheet → Print or work on paper, then Show solutions and mark each part." },
    { id: "ws2", name: "Quiz Prep: rebuild and redo the worksheet", minutes: 35, how: "Click Rebuild study kit for new numbers. Redo every part you marked ✗ first." },
    { id: "test", name: "Quiz Prep: timed practice test, no calculator", minutes: 25, how: "Practice Quiz → Generate → Start 20-min timer. Check with Show answers." }
  ];
  res.json({
    quiz: title,
    topics: ann?.topics || null, confirmedBy: ann?.source || null, lessons, slides,
    kitBuilt: !!kit, ready: { known, cards, right, marked: marks.length },
    brief: {
      gist: (ann ? `${title.replace(/\s*\(.*\)$/, "")} covers ${ann.topics} (confirmed in ${ann.source}). ` : "") +
        "Taken in Friday recitation, no calculator." + (kit ? "" : " Build the study kit first."),
      steps: steps.filter((st) => !(prog.plan || {})[st.id]).map(({ name, minutes, how }) => ({ name, minutes, how })),
      watchOut: [
        ...(ann ? [`The schedule sheet's lesson numbers are out of date; study ${ann.topics}.`] : []),
        ...(kit?.review?.traps || []).slice(0, 3)
      ],
      madeAt: "quiz-prep:" + (kit?.builtAt || "none") + ":" + (prog.updatedAt || "")
    },
    kitUrl: "http://localhost:3123/"
  });
});

app.get("/api/materials", (req, res) => res.json(findMaterials().map(({ name, kind, number }) => ({ name, kind, number }))));

const kitFile = (title) => path.join(KITS_DIR, String(title).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") + ".json");
// Rebuilding a kit keeps the version it replaces here, so old kits (and the worksheets she already did) stay viewable.
const KIT_HISTORY = path.join(KITS_DIR, "history");
function archiveKit(file) {
  if (!fs.existsSync(file)) return;
  const old = JSON.parse(fs.readFileSync(file, "utf8"));
  const stamp = String(old.builtAt || new Date().toISOString()).replace(/[:.]/g, "-").slice(0, 19);
  fs.mkdirSync(KIT_HISTORY, { recursive: true });
  fs.writeFileSync(path.join(KIT_HISTORY, path.basename(file, ".json") + "--" + stamp + ".json"), JSON.stringify(old, null, 2));
}
app.get("/api/kit", (req, res) => {
  if (req.query.id) {   // an older version from the history folder
    const f = path.join(KIT_HISTORY, String(req.query.id).replace(/[^a-z0-9-]/gi, "") + ".json");
    return res.json(fs.existsSync(f) ? JSON.parse(fs.readFileSync(f, "utf8")) : null);
  }
  const f = kitFile(req.query.quiz || "");
  res.json(fs.existsSync(f) ? JSON.parse(fs.readFileSync(f)) : null);
});
// Every saved kit, newest first: the current one for each quiz plus the older versions it replaced.
app.get("/api/kits", (req, res) => {
  const row = (file, id, current) => {
    try {
      const k = JSON.parse(fs.readFileSync(file, "utf8"));
      return { id, current, quiz: k.quiz, lessons: k.lessons || [], topics: k.topics || "", builtAt: k.builtAt || null,
        cards: (k.cards || []).length, problems: (k.worksheet?.problems || []).length };
    } catch { return null; }
  };
  const list = fs.readdirSync(KITS_DIR).filter((f) => f.endsWith(".json") && f !== "test-kit.json").map((f) => row(path.join(KITS_DIR, f), null, true));
  if (fs.existsSync(KIT_HISTORY)) for (const f of fs.readdirSync(KIT_HISTORY).filter((x) => x.endsWith(".json")))
    list.push(row(path.join(KIT_HISTORY, f), f.replace(/\.json$/, ""), false));
  res.json(list.filter(Boolean).sort((a, b) => String(b.builtAt).localeCompare(String(a.builtAt))));
});

app.post("/api/kit", async (req, res) => {
  const { quiz, lessons = [], topics = "", worksheets = [] } = req.body || {};
  if (!quiz) return res.status(400).json({ error: "No quiz chosen." });
  const mats = findMaterials();
  const slideMats = mats.filter((m) => m.kind === "slides" && lessons.includes(m.number));
  const wsMats = mats.filter((m) => m.kind === "worksheet" && worksheets.includes(m.name));
  let slides = "", sheets = "";
  try {
    for (const m of slideMats) slides += "\n=== " + m.name + " ===\n" + (await pdfText(m.file));
    for (const m of wsMats) sheets += "\n=== " + m.name + " ===\n" + (await pdfText(m.file));
  } catch (err) { return res.status(500).json({ error: "Couldn't read a PDF: " + err.message }); }
  slides = slides.slice(0, 30000); sheets = sheets.slice(0, 12000);
  const context = `Course: ${courseLine(COURSE)}. Students take a ${COURSE.quizPoints}-point quiz${COURSE.noCalculator ? " by hand" : ""}.\n${NICE_NUMBERS}
Upcoming: ${quiz}. Topics: ${topics || "Lessons " + lessons.join(", ")}.
${slides ? "LECTURE SLIDES (the source of truth: use their notation, formulas and decision rules):\n" + slides : "No slides were found, so stick to standard intro-statistics methods for these topics."}`;
  // Regenerate up to 3 times; keep the version with the fewest messy numbers (plus any other problems offBy counts).
  const cleanest = async (make, offBy = () => 0) => {
    let best = null;
    for (let i = 0; i < 3; i++) {
      const out = await make();
      out.messy = messyNumbers(JSON.stringify(out));
      const score = out.messy.length + offBy(out);
      if (!best || score < best.score) best = { out, score };
      if (!best.score) break;
    }
    return best.out;
  };
  // Her marks on the last worksheet decide the next one's mix: mostly what she missed, some she got right.
  let prevKit = null, marked = { missed: [], right: [] };
  try {
    prevKit = fs.existsSync(kitFile(quiz)) ? JSON.parse(fs.readFileSync(kitFile(quiz))) : null;
    marked = markedParts(prevKit?.worksheet, (readProgress()[quiz] || {}).marks || {});
  } catch {}
  const mix = focusPlan(marked.missed.length, marked.right.length);
  const list = (xs) => xs.map((t) => "- " + t).join("\n");
  const mixText = !mix ? `Set "focus":"new" on every problem.` : `Her marks from the last worksheet decide the mix: EXACTLY ${mix.missed} "missed", ${mix.kept} "kept" and ${mix.fresh} "new" problems.
- Problems 1-${mix.missed}: NEW versions of the skills she MISSED. Every item below comes back at least once as the same KIND of question (a "more than" stays a right tail, a "between" stays a between, a "verify" stays a verify); combine several into one multi-part problem if needed. Use new contexts and new numbers: never copy a number set from this list. Set "focus":"missed".
${list(marked.missed)}${mix.kept ? `
- Problems ${mix.missed + 1}-${mix.missed + mix.kept}: NEW versions of skills she got RIGHT, so they stay fresh. Set "focus":"kept".
${list(marked.right)}` : ""}${mix.fresh ? `
- The other ${mix.fresh}: quiz topics the lists above don't cover. Set "focus":"new".` : ""}`;
  const onlySheet = req.body.only === "worksheet";
  if (onlySheet && !prevKit) return res.status(400).json({ error: "Build the study kit once first." });
  if (onlySheet && !sheets) return res.status(400).json({ error: "Tick at least one worksheet in Build settings first." });
  const ask = async (task, maxTokens = 4000) => pullJSON(await askAI({ prompt: context + "\n\nTASK:\n" + task, maxTokens, model: "openai/gpt-4o" }));
  try {
    const [review, cards, redo] = await Promise.all([
      // a new worksheet alone keeps the kit's Review and Flashcards
      onlySheet ? Promise.resolve(prevKit.review) : ask(`Write a short, plain-English lesson for a student who missed class, covering everything on the quiz.
Return JSON ONLY: {"bigIdea":string,
 "sections":[{"heading":string,"points":[string],"example":{"problem":string,"steps":[string],"answer":string}}],
 "symbols":[{"symbol":string,"say":string,"means":string}],
 "formulas":[{"name":string,"formula":string,"use":string}],
 "steps":[{"name":string,"steps":[string]}],
 "traps":[string]}
"steps" are the step-by-step recipes for each problem type. "traps" are the common mistakes and trick questions.
Use plain text math: ^ for powers, sqrt( ), Greek letters as symbols (μ σ p̂ x̄ α H₀ Hₐ). Keep sentences short.`),
      onlySheet ? Promise.resolve({ cards: prevKit.cards }) : ask(`Write 24 flashcards that cover every definition, symbol, formula, decision rule and common trap for this quiz.
Mix kinds: "concept" (what is it), "symbol" (what does it mean), "formula" (write it), "decide" (a tiny scenario: what do you conclude?).
Return JSON ONLY: {"cards":[{"kind":string,"front":string,"back":string}]}. Backs are 1-3 short lines.`),
      sheets ? cleanest(() => ask(`Here are the student's past worksheets. They practice by redoing worksheets, so write a FRESH worksheet on THIS quiz's topics
with the same style, layout and difficulty as these worksheets (same kind of multi-part numbered problems), but new numbers and contexts.
IMPORTANT: the worksheets below show STYLE ONLY. Every problem must test the quiz topics (${topics}) using the slides' methods, never the worksheets' own topics.
${sheets}
Write 6 problems. Each problem has a full worked solution. Write math as plain text (√, ×, ≥, x̄, p̂, σ, μ), never LaTeX.
${mixText}
Title it exactly "${String(quiz).replace(/\s*\(.*\)$/, "")} practice worksheet". Never reuse a real worksheet name or number.
${STATS && /sampling|central limit|standard error|proportion|x̄|mean/i.test(topics) ? "USE ONLY THESE NUMBER SETS (one set per problem, copy the numbers exactly, never compute new decimals; every value and probability you need is already in the set):\n" + JSON.stringify(numberBank(8)) : "Choose numbers that work out by hand."}
Return JSON ONLY: {"title":string,"problems":[{"number":int,"focus":"missed"|"kept"|"new","text":string,"parts":[{"label":string,"text":string,"solution":string,"answer":string}],"solution":string,"answer":string}]}
Use parts for (a),(b)...; if a problem has no parts, fill its own solution and answer.`, 5000), (out) => mixOff(out.problems, mix)) : Promise.resolve(null)
    ]);
    const plain = (o) => ["text", "solution", "answer"].forEach((f) => { if (o[f] != null) o[f] = plainMath(o[f]); });
    for (const p of redo?.problems || []) {
      p.focus = ["missed", "kept"].includes(p.focus) ? p.focus : "new";
      plain(p); (p.parts || []).forEach(plain);
    }
    if (redo) { try { await checkSheet(redo, slides); redo.checked = true; } catch { redo.checked = false; } }
    const kit = { quiz, lessons, topics, builtAt: new Date().toISOString(),
      sources: [...slideMats, ...wsMats].map((m) => m.name), review, cards: cards.cards || [], worksheet: redo, mix };
    archiveKit(kitFile(quiz));
    fs.writeFileSync(kitFile(quiz), JSON.stringify(kit, null, 2));
    // New worksheet, new problem numbers: archive the old ✓/✗ marks (they still count toward skill).
    const allP = readProgress();
    if (allP[quiz]?.marks && Object.keys(allP[quiz].marks).length) {
      allP[quiz].past = [...(allP[quiz].past || []), ...Object.values(allP[quiz].marks)];
      allP[quiz].marks = {};
      fs.writeFileSync(PROGRESS, JSON.stringify(allP, null, 2));
    }
    res.json(kit);
  } catch (err) {
    res.status(502).json({ error: err.message });
  }
});

// Checkers must use the professor's rounded cutoffs (±2, not ±1.96), or they flag right answers.
const COURSE_CUTOFFS = courseCutoffs(COURSE);

// Worksheets get the same second opinion as practice quizzes: solve every part from scratch, flag disagreements.
// (A worksheet once said √(0.16/256) = 0.04, and she would have marked her right answer wrong.)
async function checkSheet(w, notes) {
  const items = [];
  (w.problems || []).forEach((p, pi) => {
    if (p.parts?.length) p.parts.forEach((x, xi) => items.push({ key: pi + "." + xi, question: p.text + " " + x.text, given: x.answer }));
    else items.push({ key: String(pi), question: p.text, given: p.answer });
  });
  const prompt = `You are checking a statistics worksheet's answer key. For EACH item, solve it yourself from scratch, step by step, BEFORE looking at the given answer. Then decide if the given answer is correct.
${COURSE_CUTOFFS}
${notes ? "Course slides (use their conventions):\n" + notes.slice(0, 12000) + "\n" : ""}Items:
${JSON.stringify(items.map(({ key, question }) => ({ key, question })))}
Given answers:
${JSON.stringify(items.map(({ key, given }) => ({ key, given })))}
Return JSON ONLY: {"checks":[{"key":string,"work":string,"yourAnswer":string,"agrees":boolean,"note":string}]}
"note" explains any problem in one sentence (empty if fine).`;
  const checked = pullJSON(await askAI({ prompt, maxTokens: 4000, model: "openai/gpt-4o" }));
  for (const c of checked.checks || []) {
    const item = items.find((x) => x.key === c.key);
    if (c.agrees || (item && sameAnswer(c.yourAnswer, item.given))) continue;
    const [pi, xi] = String(c.key).split(".").map(Number);
    const target = Number.isInteger(xi) ? w.problems[pi]?.parts?.[xi] : w.problems[pi];
    if (target) target.flag = "Checker got: " + plainMath(c.yourAnswer || "?") + (c.note ? ". " + plainMath(c.note) : "");
  }
}

// ── New lesson: the newest slides taught in small visual chunks, after a recap of last week ──
const { cleanLesson, lessonGaps, examplePageGroups, PROMPT_HOOKS } = require("./lib/lesson");
const LESSONS_DIR = path.join(__dirname, "data", "lessons");
const lessonFile = (n) => path.join(LESSONS_DIR, "lesson-" + Number(n) + ".json");
const lessonTitle = (name) => name.replace(/^.*Lesson\s*\d+\s*[-–]\s*/i, "").replace(/\s*Part\s+[IVX\d]+.*$|\s*Annotated.*$/i, "").trim();

app.get("/api/lessons", (req, res) => {
  const byNum = new Map();
  for (const m of findMaterials()) if (m.kind === "slides" && !byNum.has(m.number))
    byNum.set(m.number, { number: m.number, title: lessonTitle(m.name), built: fs.existsSync(lessonFile(m.number)) });
  res.json([...byNum.values()].sort((a, b) => b.number - a.number));
});
app.get("/api/lesson", (req, res) => {
  const f = lessonFile(req.query.n);
  res.json(fs.existsSync(f) ? JSON.parse(fs.readFileSync(f, "utf8")) : null);
});

const lessonPrompt = ({ n, now, prevN, before, examplePages = [] }) => `Course: ${courseLine(COURSE)}.${COURSE.noCalculator ? " Quizzes are by hand, no calculator." : ""}
${NICE_NUMBERS}
Turn THIS WEEK's lecture slides into a very visual lesson that is easy to remember, for ${PROFILE.learner || "a student"} who learns best from pictures and small steps.
Teach EVERYTHING on the slides (every definition, formula, decision rule and worked example), in the slides' notation and order, in the plainest words possible.
- Aim for 7-8 chunks: one per slide topic, small enough to take in at a glance.
${STATS ? `- Every worked example on the slides becomes its own chunk whose "example" is a Calc with ITS numbers${examplePages.length ? ` (worked examples are on pages ${examplePages.map((g) => g.join("/")).join(", ")})` : ""}. Never do that arithmetic yourself: the app computes the standard error, z, the cutoff and the decision, writes the steps and draws the curve that marks where the sample landed.` : `- Every worked example on the slides becomes its own chunk with ITS numbers and steps.`}
- "idea" is concrete: say what it means using the slides' own example${STATS ? " (the soda cans, not \"a parameter\")" : ", not abstract words"}.
- "hook" is a real memory trick in the style of ${PROMPT_HOOKS.map((h) => JSON.stringify(h)).join(" / ")}: a rhyme, a vivid picture, an acronym or an analogy about THIS idea, never a restated definition. Bad: "Critical values: rejection borders." Each chunk's hook is different.
- Each "check" has exactly ONE right choice by the slides' own definitions; no trick or debatable wording. Checks test understanding${STATS ? " (which tail, what α means, what to conclude)" : ""}, not arithmetic.

THIS WEEK: Lesson ${n}
${now}
${before ? `LAST WEEK: Lesson ${prevN} (only for a 3-minute recap)\n${before}` : ""}

Return JSON ONLY:
{"title": string (the lesson's short name),
 "recap": ${before ? `{"title": string, "rule": string (the ONE sentence to remember from last week), "diagram": Diagram|null, "recall": [{"q": string, "a": string}] (2-3 quick questions on last week; answers are one line)}` : "null"},
 "chunks": [5 to 8 chunks, one idea each, in the slides' order:
   {"title": string (6 words max), "idea": string (one plain sentence, 25 words max),
    "diagram": Diagram|null,
    "example": {"problem": string (the slide's question, one sentence), "calc": Calc} for any test, confidence interval or sample size
             | {"problem": string, "steps": [string] (2-5 short steps), "answer": string} for anything else, with no arithmetic | null,
    "hook": string (a memory trick: rhyme, picture, acronym or analogy, 15 words max),
    "check": {"q": string, "choices": [string] (3-4), "answer": int (index of the right choice, 0-based), "why": string (1-2 sentences)},
    "page": int (the [page N] it comes from) | null}]}

${STATS ? `A Calc copies the numbers off the slide (the app does ALL the math):
 {"type":"z-test-mean","claim":μ₀,"xbar":x̄,"sd":σ,"n":n,"alpha":0.01|0.05|0.1,"tail":"left"|"right"|"two","ifReject":string,"ifFail":string}
 {"type":"z-test-prop","claim":p₀,"phat":p̂ OR "count": number of successes,"n":n,"alpha":…,"tail":…,"ifReject":string,"ifFail":string}
 {"type":"ci-mean","xbar":x̄,"sd":σ or s,"n":n,"level":90|95|99}   {"type":"ci-prop","phat":p̂ OR "count","n":n,"level":90|95|99}
 {"type":"size-mean","sd":σ,"E":margin of error,"level":…}   {"type":"size-prop","p":p (0.5 if unknown),"E":…,"level":…}
 "ifReject"/"ifFail": one sentence each, answering the slide's question in its own words for that outcome.
 the soda cans: {"problem":"Do the cans hold less than 12 oz on average?","calc":{"type":"z-test-mean","claim":12,"xbar":11.85,"sd":0.5,"n":100,"alpha":0.05,"tail":"left","ifReject":"Yes: the cans hold less than 12 oz, so the company's claim is wrong.","ifFail":"There isn't enough evidence that the cans hold less than 12 oz."}}
A chunk with a Calc example gets its curve and check question from the app: leave its "diagram" and "check" null.

` : ""}
A Diagram is ONE of these. Pick the type that SHOWS the idea, and make its numbers match the idea exactly:
 {"type":"bell","shade":"left"|"right"|"both"|"middle","cut":number (z cutoff, positive, at most 4),"areaLabel":string,"mark":number|null (a z test statistic to mark),"markLabel":string|null,"mean":number|null,"se":number|null}
   one-tailed left test at α = 0.05: {"type":"bell","shade":"left","cut":1.65,"areaLabel":"α = 0.05"}
   two-tailed at α = 0.05 (label each tail): {"type":"bell","shade":"both","cut":2,"areaLabel":"α/2 = 0.025"}
   95% confidence: {"type":"bell","shade":"middle","cut":2,"areaLabel":"95%"}
   the soda example, sample at z = −3: add "mark":-3,"markLabel":"your sample: z = −3","mean":12,"se":0.05
 {"type":"interval","center":number,"margin":number,"centerLabel":string,"mark":number|null,"markLabel":string|null}
   a CI of 50 ± 4 with the claimed μ₀ = 52 inside: {"type":"interval","center":50,"margin":4,"centerLabel":"x̄ = 50","mark":52,"markLabel":"μ₀ = 52 is inside"}
 {"type":"flow","steps":[string] (2-6 steps, 8 words max each)}
 {"type":"formula","parts":[{"text":string,"label":string|null,"role":"stat"|"param"|"spread"|"size"|"result"|"op"}]}
   z = (x̄ − μ₀)/(σ/√n): [{"text":"z","label":"test statistic","role":"result"},{"text":"=","role":"op"},{"text":"(","role":"op"},{"text":"x̄","label":"sample mean","role":"stat"},{"text":"−","role":"op"},{"text":"μ₀","label":"claimed mean","role":"param"},{"text":")","role":"op"},{"text":"/","role":"op"},{"text":"(","role":"op"},{"text":"σ","label":"population SD","role":"spread"},{"text":"/","role":"op"},{"text":"√n","label":"sample size","role":"size"},{"text":")","role":"op"}]
 {"type":"compare","columns":[{"head":string,"items":[string]}] (2-3 columns, 5 items max each)}
Give at least 5 chunks a diagram (Calc chunks count). Use the course's critical values above. Every number must work by hand.
Write math as plain text (√, ×, ≥, x̄, p̂, σ, μ, α, H₀, Hₐ), never LaTeX.`;

// Second opinion, like quizzes and worksheets: re-solve every check question and example, flag disagreements.
async function checkLesson(lesson, notes) {
  const items = [];
  lesson.chunks.forEach((c, i) => {
    if (c.computed) return;   // the app did that math itself
    if (c.check) items.push({ key: "c" + i, question: c.check.q + "\n" + c.check.choices.map((x, j) => "ABCD"[j] + ") " + x).join("\n"), given: "ABCD"[c.check.answer] + ") " + c.check.choices[c.check.answer] });
    if (c.example) items.push({ key: "e" + i, question: c.example.problem, given: c.example.answer });
  });
  if (!items.length) return;
  const prompt = `You are checking a statistics lesson. For EACH item, solve it yourself from scratch BEFORE looking at the given answer, then decide if the given answer is correct. For multiple choice, also check that exactly one choice is correct.
${COURSE_CUTOFFS}
${notes ? "Course slides (use their conventions):\n" + notes.slice(0, 12000) + "\n" : ""}Items:
${JSON.stringify(items.map(({ key, question }) => ({ key, question })))}
Given answers:
${JSON.stringify(items.map(({ key, given }) => ({ key, given })))}
Return JSON ONLY: {"checks":[{"key":string,"yourAnswer":string,"agrees":boolean,"note":string}]}`;
  const checked = pullJSON(await askAI({ prompt, maxTokens: 3000, model: "openai/gpt-4o" }));
  for (const c of checked.checks || []) {
    const item = items.find((x) => x.key === c.key);
    if (c.agrees || (item && sameAnswer(c.yourAnswer, item.given))) continue;
    const chunk = lesson.chunks[Number(String(c.key).slice(1))];
    if (!chunk) continue;
    const what = String(c.key)[0] === "c" ? "check question" : "example";
    chunk.flag = (chunk.flag ? chunk.flag + " " : "") + `For the ${what}, the checker got ${plainMath(c.yourAnswer || "?")}${c.note ? ". " + plainMath(c.note) : ""}.`;
  }
}

app.post("/api/lesson", async (req, res) => {
  const n = Number(req.body?.number);
  const slides = findMaterials().filter((m) => m.kind === "slides");
  const parts = slides.filter((m) => m.number === n);
  if (!parts.length) return res.status(404).json({ error: `No slides for Lesson ${n} in Downloads.` });
  const prevN = Math.max(0, ...slides.filter((m) => m.number < n).map((m) => m.number)) || null;
  const prevParts = slides.filter((m) => m.number === prevN);
  let now = "", before = "";
  try {
    for (const m of parts) now += "\n=== " + m.name + " ===\n" + (await pdfText(m.file));
    for (const m of prevParts) before += "\n=== " + m.name + " ===\n" + (await pdfText(m.file));
  } catch (err) { return res.status(500).json({ error: "Couldn't read a PDF: " + err.message }); }
  now = now.slice(0, 30000); before = before.slice(0, 12000);
  // Pages with a worked example ("Example 2…"), so none get skipped. Page numbers restart per part, so only for one-part lessons.
  const examplePages = parts.length === 1 ? examplePageGroups(now) : [];
  // Up to 3 tries: each one hears what the last one was missing (too few chunks, no diagrams, unfinished examples).
  let lesson = null, gaps = [], lastErr = null;
  for (let attempt = 0; attempt < 3; attempt++) {
    const ask = lessonPrompt({ n, now, prevN, before, examplePages }) + (gaps.length ? "\n\nYour last try was sent back because:\n- " + gaps.join("\n- ") + "\nFix all of these." : "");
    try {
      const got = cleanLesson(pullJSON(await askAI({ prompt: ask, maxTokens: 7000, model: "openai/gpt-4o" })), { number: n, prevNumber: prevN });
      const g = lessonGaps(got, { examplePages, calc: STATS });
      if (!lesson || g.length < lessonGaps(lesson, { examplePages, calc: STATS }).length) lesson = got;
      gaps = g;
      if (!g.length) break;
    } catch (err) { lastErr = err; }
  }
  if (!lesson) return res.status(502).json({ error: (lastErr && lastErr.message) || "Couldn't build the lesson." });
  try { await checkLesson(lesson, now); lesson.checked = true; } catch { lesson.checked = false; }
  Object.assign(lesson, { number: n, builtAt: new Date().toISOString(), sources: [...parts, ...prevParts].map((m) => m.name) });
  fs.mkdirSync(LESSONS_DIR, { recursive: true });
  fs.writeFileSync(lessonFile(n), JSON.stringify(lesson, null, 2));
  res.json(lesson);
});

// ── Ask chatbot: questions about whatever is on her screen, answered from the slides ──
const { askPrompt } = require("./lib/ask");
app.post("/api/ask", async (req, res) => {
  const { question, where, screen, lessons = [], history = [] } = req.body || {};
  if (!String(question || "").trim()) return res.status(400).json({ error: "Type a question first." });
  const nums = (Array.isArray(lessons) ? lessons : []).map(Number).filter(Number.isInteger).slice(0, 4);
  let slides = "";
  try {
    for (const m of findMaterials().filter((x) => x.kind === "slides" && nums.includes(x.number))) slides += "\n=== " + m.name + " ===\n" + (await pdfText(m.file));
  } catch {}
  try {
    const answer = await askAI({ prompt: askPrompt({ question: String(question).slice(0, 2000), where: String(where || "").slice(0, 200),
      screen: String(screen || ""), slides: slides.slice(0, 14000), history: Array.isArray(history) ? history : [], cutoffs: COURSE_CUTOFFS,
      name: PROFILE.name, course: courseLine(COURSE), noCalculator: COURSE.noCalculator, style: PROFILE.chatStyle || undefined }),
      maxTokens: 4000, model: "openai/gpt-5" });
    res.json({ answer: plainMath(answer).replace(/\*\*(.+?)\*\*/g, "$1").trim() || "I didn't get an answer back. Try asking again." });
  } catch (err) { res.status(502).json({ error: "Couldn't reach the AI: " + err.message }); }
});

// ── Study progress per quiz (flashcards known, worksheet marks, plan checklist) ──
const PROGRESS = path.join(__dirname, "data", "progress.json");
const readProgress = () => { try { return JSON.parse(fs.readFileSync(PROGRESS, "utf8")); } catch { return {}; } };
app.get("/api/progress", (req, res) => res.json(readProgress()[req.query.quiz] || {}));
app.post("/api/progress", (req, res) => {
  const { quiz, patch } = req.body || {};
  if (!quiz || typeof patch !== "object") return res.status(400).json({ error: "bad progress" });
  const all = readProgress();
  all[quiz] = { ...(all[quiz] || {}), ...patch, updatedAt: new Date().toISOString() };
  fs.writeFileSync(PROGRESS, JSON.stringify(all, null, 2));
  res.json(all[quiz]);
});



// ── Computed questions: the code does the math, so the answer key is always right ──
const shuffle = (a) => { a = a.slice(); for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; };
const fmt = (x) => String(r4(x));
function mc(q, right, wrongs, w) {
  const opts = [right, ...[...new Set(wrongs.filter((x) => x !== right))].slice(0, 3)];
  while (opts.length < 4) opts.push("None of these");
  const o = shuffle(opts);
  return { q, o, a: o.indexOf(right), w, computed: true };
}
const CONTEXTS = [["battery life", "hours"], ["commute time", "minutes"], ["exam score", "points"], ["coffee spending", "dollars"], ["sleep", "minutes"], ["package weight", "ounces"]];
const PROPS = [["students who bike to campus"], ["voters who support a new park"], ["phones with a cracked screen"], ["customers who return an item"]];
const QUESTION_MAKERS = {
  // Lesson 8: sampling distributions
  8: [
    () => { const b = numberBank(10).find((x) => x.kind === "mean"); const [c, u] = pick(CONTEXTS);
      return mc(`Mean ${c} is ${b.mu} ${u} with σ = ${b.sigma}. For samples of n = ${b.n}, what is σx̄?`, fmt(b.se), [fmt(b.sigma), fmt(b.sigma / b.n), fmt(b.se * 2)],
        [`σx̄ = σ / √n = ${b.sigma} / ${b.sqrt_n}`, `= ${fmt(b.se)}`]); },
    () => { const b = numberBank(10).find((x) => x.kind === "mean");
      return mc(`μ = ${b.mu}, σ = ${b.sigma}, n = ${b.n}. Find P(x̄ < ${b.value_below}).`, fmt(b.P_below), [fmt(1 - b.P_below), fmt(b.P_between), fmt(0.5)],
        [`σx̄ = ${b.sigma} / ${b.sqrt_n} = ${fmt(b.se)}`, `z = (${b.value_below} − ${b.mu}) / ${fmt(b.se)} = −${b.z}`, `left tail = ${fmt(b.P_below)}`]); },
    () => { const b = numberBank(10).find((x) => x.kind === "proportion");
      return mc(`p = ${b.p}, n = ${b.n}. What is the standard deviation of p̂?`, fmt(b.se), [fmt(b.p_times_1_minus_p), fmt(b.se * 2), fmt(b.p_times_1_minus_p / b.n)],
        [`√( ${b.p} × ${fmt(1 - b.p)} / ${b.n} ) = √${fmt(b.p_times_1_minus_p)} / √${b.n}`, `= ${fmt(b.se)}`]); }
  ],
  // Lesson 9: confidence intervals (95% -> z = 2, 90% -> z = 1.65)
  9: [
    () => { const b = numberBank(10).find((x) => x.kind === "mean"); const [c, u] = pick(CONTEXTS);
      const xbar = b.mu, E = 2 * b.se;
      return mc(`A sample of ${b.n} has mean ${c} ${xbar} ${u}, σ = ${b.sigma}. Find the 95% confidence interval (z = 2).`,
        `(${fmt(xbar - E)}, ${fmt(xbar + E)})`,
        [`(${fmt(xbar - b.se)}, ${fmt(xbar + b.se)})`, `(${fmt(xbar - 1.65 * b.se)}, ${fmt(xbar + 1.65 * b.se)})`, `(${fmt(xbar - 2 * b.sigma)}, ${fmt(xbar + 2 * b.sigma)})`],
        [`SE = ${b.sigma} / ${b.sqrt_n} = ${fmt(b.se)}`, `E = 2 × ${fmt(b.se)} = ${fmt(E)}`, `${xbar} ± ${fmt(E)}`]); },
    () => { const n = pick([25, 100, 400]), root = Math.sqrt(n), se = pick([2, 4, 10, 20]), sigma = se * root, xbar = 5 * Math.round((50 + Math.random() * 500) / 5), E = r4(1.65 * se);
      return mc(`n = ${n}, x̄ = ${xbar}, s = ${sigma}. Find the 90% confidence interval (z = 1.65).`,
        `(${fmt(xbar - E)}, ${fmt(xbar + E)})`, [`(${fmt(xbar - 2 * se)}, ${fmt(xbar + 2 * se)})`, `(${fmt(xbar - se)}, ${fmt(xbar + se)})`, `(${fmt(xbar - 1.65 * sigma)}, ${fmt(xbar + 1.65 * sigma)})`],
        [`SE = ${sigma} / ${root} = ${se}`, `E = 1.65 × ${se} = ${fmt(E)}`, `${xbar} ± ${fmt(E)}`]); },
    () => { const b = numberBank(10).find((x) => x.kind === "proportion"); const [what] = pick(PROPS); const E = 2 * b.se;
      return mc(`In a sample of ${b.n}, the proportion of ${what} is p̂ = ${b.p}. Find the 95% confidence interval.`,
        `(${fmt(b.p - E)}, ${fmt(b.p + E)})`, [`(${fmt(b.p - b.se)}, ${fmt(b.p + b.se)})`, `(${fmt(b.p - 1.65 * b.se)}, ${fmt(b.p + 1.65 * b.se)})`, `(${fmt(b.p - 0.1)}, ${fmt(b.p + 0.1)})`],
        [`SE = √( ${b.p} × ${fmt(1 - b.p)} / ${b.n} ) = ${fmt(b.se)}`, `E = 2 × ${fmt(b.se)} = ${fmt(E)}`, `${b.p} ± ${fmt(E)}`]); },
    () => { const [sigma, E] = pick([[20, 2], [10, 1], [30, 3], [15, 1.5], [40, 4], [25, 5]]); const n = (2 * sigma / E) ** 2;
      return mc(`σ = ${sigma}. How big must n be for a 95% margin of error of E = ${E}? (z = 2)`, String(n), [String(2 * sigma / E), String(n / 2), String(n * 4)],
        [`n = (zσ / E)² = (2 × ${sigma} / ${E})²`, `= ${2 * sigma / E}²`, `= ${n}`]); },
    () => mc(`What happens to a confidence interval when the confidence level goes from 90% to 95%?`, "It gets wider (z goes from 1.65 to 2)",
        ["It gets narrower", "It stays the same width", "Only the center moves"], ["Higher confidence needs a bigger z", "Bigger z → bigger margin of error → wider interval"]),
    () => mc(`Using the most conservative estimate for a 95% interval with E = 0.05, what sample size do you need?`, "400",
        ["100", "200", "1600"], ["Most conservative: p = 0.5, so p(1 − p) = 0.25", "n = 2² × 0.25 / 0.05² = 1 / 0.0025", "= 400"])
  ],
  // Lesson 10: hypothesis tests with z
  10: [
    () => { const b = numberBank(10).find((x) => x.kind === "mean"); const left = Math.random() < 0.5;
      const xbar = left ? b.value_below : b.value_above, z = left ? -b.z : b.z;
      return mc(`H₀: μ = ${b.mu}, Hₐ: μ ${left ? "<" : ">"} ${b.mu}. σ = ${b.sigma}, n = ${b.n}, x̄ = ${xbar}. What is the test statistic z?`, fmt(z), [fmt(-z), fmt((xbar - b.mu) / b.sigma), fmt(z * 2)],
        [`σx̄ = ${b.sigma} / ${b.sqrt_n} = ${fmt(b.se)}`, `z = (${xbar} − ${b.mu}) / ${fmt(b.se)} = ${fmt(z)}`]); },
    () => { const [a, zc, word] = pick([[0.05, "−1.65", "<"], [0.01, "−2.33", "<"], [0.1, "−1.28", "<"], [0.05, "1.65", ">"], [0.01, "2.33", ">"], [0.05, "±2", "≠"]]);
      return mc(`Hₐ uses "${word}" and α = ${a}. What is the critical value?`, zc, ["−1.65", "1.65", "±2", "−2.33", "2.33", "−1.28"].filter((x) => x !== zc).slice(0, 3),
        [`"${word}" is a ${word === "<" ? "left" : word === ">" ? "right" : "two"}-tailed test`, `α = ${a} → z_c = ${zc} (course table)`]); },
    () => { const z = pick([-1, -1.5, -2, -2.5, -3]), [a, zc] = pick([[0.05, -1.65], [0.01, -2.33], [0.1, -1.28]]); const reject = z < zc;
      return mc(`Left-tailed test, α = ${a}, test statistic z = ${z}. Decision?`, reject ? "Reject H₀" : "Fail to reject H₀", [reject ? "Fail to reject H₀" : "Reject H₀", "Accept Hₐ and H₀", "Not enough information"],
        [`Critical value z_c = ${zc}`, `${z} is ${reject ? "past" : "not past"} ${zc} (${reject ? "in" : "outside"} the rejection region)`, reject ? "So reject H₀" : "So fail to reject H₀"]); },
    () => { const b = numberBank(10).find((x) => x.kind === "proportion"); const [what] = pick(PROPS); const ph = b.phat_below;
      return mc(`Claim: ${b.p * 100}% of ${what}. Sample of ${b.n} gives p̂ = ${ph}. Test statistic z?`, fmt(-b.z), [fmt(b.z), fmt((ph - b.p) / b.p), fmt(-b.z / 2)],
        [`σp̂ = √( ${b.p} × ${fmt(1 - b.p)} / ${b.n} ) = ${fmt(b.se)}`, `z = (${ph} − ${b.p}) / ${fmt(b.se)} = ${fmt(-b.z)}`]); },
    () => mc(`A company claims bulbs last at least 800 hours; you suspect less. Which hypotheses?`, "H₀: μ = 800, Hₐ: μ < 800",
        ["H₀: μ < 800, Hₐ: μ = 800", "H₀: μ = 800, Hₐ: μ > 800", "H₀: μ ≠ 800, Hₐ: μ = 800"], ["H₀ always has the equals sign", "Hₐ is what you suspect: less than 800"])
  ]
};
function computedQuestions(lesson, count) {
  const makers = QUESTION_MAKERS[lesson]; if (!makers) return [];
  return shuffle(makers).slice(0, count).map((f) => f());
}

// ── Exam mode: per-lesson skill + a study schedule up to the exam ──
const SKILLS = path.join(__dirname, "data", "skills.json");
const readSkills = () => { try { return JSON.parse(fs.readFileSync(SKILLS, "utf8")); } catch { return {}; } };

async function plannerCourse() {
  const r = await fetch(PLANNER_URL);
  const data = await r.json();
  return (data.courses || []).find((c) => c.key === COURSE_KEY) || null;
}

// "Exam 2 (Lessons 9 - 13) (Lectures 12 - 18)" -> [9..13]
function examLessons(title) {
  const m = String(title).match(/Lessons?\s*(\d+)\s*[-–]\s*(\d+)/i);
  if (!m) return lessonNumbers(title);
  const out = []; for (let n = +m[1]; n <= +m[2]; n++) out.push(n); return out;
}

// Lesson names from everything we have: slide files, the planner's briefs and materials.
function lessonNames(course) {
  const names = {};
  const add = (n, t) => { t = String(t || "").replace(/\s*(Part\s+[IVX]+|Annotated|\.pdf)\b.*$/i, "").trim(); if (t && !names[n]) names[n] = t; };
  for (const m of findMaterials().filter((x) => x.kind === "slides"))
    add(m.number, m.name.replace(/^.*Lesson\s*\d+\s*[-–]\s*/i, ""));
  for (const d of course?.deadlines || [])
    for (const m of String(d.brief?.gist || "").matchAll(/Lesson\s+(\d+)\s*[–-]\s*([A-Z][^,;.()]+?)(?=\s+and\s+Lesson|,|;|\.|\(|$)/g)) add(+m[1], m[2]);
  for (const m of course?.materials || []) { const x = String(m.url || "").match(/Lesson\s*(\d+)\s*-\s*([^/]+?)(?:\s+Part|\s+Annotated|\.pdf)/i); if (x) add(+x[1], decodeURIComponent(x[2])); }
  return names;
}

// Skill for one lesson, 0-100, from: skill checks (newest weighs most), worksheet ✓/✗, real quiz scores.
function lessonSkill(n, course, skills, progress) {
  const parts = [], why = [];
  const checks = (skills[n]?.checks || []).slice(-3);
  if (checks.length) {
    const w = checks.map((_, i) => i + 1), tot = w.reduce((a, b) => a + b, 0);
    const pct = checks.reduce((a, c, i) => a + w[i] * (c.score / c.of), 0) / tot;
    parts.push([pct, 3]); why.push(`skill check ${Math.round(pct * 100)}%`);
  }
  let right = 0, marked = 0;
  for (const [quiz, p] of Object.entries(progress)) {
    const kf = kitFile(quiz); if (!fs.existsSync(kf)) continue;
    const kit = JSON.parse(fs.readFileSync(kf)); if (!(kit.lessons || []).includes(n)) continue;
    for (const v of [...(p.past || []), ...Object.values(p.marks || {})]) { marked++; if (v === "right") right++; }
  }
  if (marked) { parts.push([right / marked, 2]); why.push(`worksheet ${right}/${marked}`); }
  const qz = course?.grades?.categories?.find((c) => /quiz/i.test(c.name));
  for (const d of course?.deadlines || []) {
    if (!/^quiz/i.test(d.title)) continue;
    // The professor's slides can move a quiz's topics; a built kit knows the real lessons.
    const kf = kitFile(d.title), real = fs.existsSync(kf) ? JSON.parse(fs.readFileSync(kf)).lessons : null;
    if (!(real || lessonNumbers(d.title)).includes(n)) continue;
    const num = (d.title.match(/Quiz\s*(\d+)/i) || [])[1];
    const g = qz?.items?.find((it) => new RegExp("Quiz\\s*" + num + "\\b", "i").test(it.name));
    if (g) { parts.push([g.points / g.outOf, 2]); why.push(`${g.name} ${g.points}/${g.outOf}`); }
  }
  if (!parts.length) return { skill: null, why: ["not measured yet"] };
  const w = parts.reduce((a, [, x]) => a + x, 0);
  return { skill: Math.round(100 * parts.reduce((a, [v, x]) => a + v * x, 0) / w), why };
}

app.get("/api/exam", async (req, res) => {
  let course;
  try { course = await plannerCourse(); } catch { return res.status(503).json({ error: "Open the Today app so I can read your exam date." }); }
  const now = Date.now();
  const exam = (course?.deadlines || []).filter((d) => /^exam/i.test(d.title) && Date.parse(d.due) > now)
    .sort((a, b) => Date.parse(a.due) - Date.parse(b.due))[0];
  if (!exam) return res.json(null);
  const lessons = examLessons(exam.title), names = lessonNames(course);
  const mats = findMaterials(), skills = readSkills(), progress = readProgress();
  res.json({
    title: exam.title.replace(/\s*\(Lectures.*\)$/i, ""), due: exam.due,
    lessons: lessons.map((n) => ({
      n, name: names[n] || "Lesson " + n,
      slides: mats.filter((m) => m.kind === "slides" && m.number === n).map((m) => m.name),
      ...lessonSkill(n, course, skills, progress)
    }))
  });
});

// A 6-question skill check for one lesson, from its slides; clean numbers where it can.
app.post("/api/skillcheck", async (req, res) => {
  const n = Number(req.body?.lesson), name = String(req.body?.name || "Lesson " + n);
  let notes = "";
  for (const m of findMaterials().filter((x) => x.kind === "slides" && x.number === n)) notes += "\n=== " + m.name + " ===\n" + (await pdfText(m.file));
  if (!notes) return res.status(404).json({ error: `No slides for Lesson ${n} in Downloads yet. Download them from ${lmsName(PROFILE)} first.` });
  const computed = STATS ? computedQuestions(n, 4) : [];   // app-computed z/CI questions are statistics-only
  const aiCount = computed.length ? 2 : 6;
  try {
    const out = pullJSON(await askAI({ model: "openai/gpt-4o", maxTokens: 2500, prompt:
`Write ${aiCount} multiple-choice ${computed.length ? "CONCEPT questions (definitions, interpretation, when to use what; NO arithmetic)" : "questions"} for a skill check on Lesson ${n} (${name}) of ${COURSE.shortName}.
${computed.length ? "" : NICE_NUMBERS + "\nIf a question needs arithmetic, keep it to one exact step and double-check it."}
Exactly one correct option each, 4 options.
Slides (source of truth):
${notes.slice(0, 20000)}
Return JSON ONLY: {"questions":[{"q":string,"o":[string,string,string,string],"a":int,"w":[string]}]} where w is 2-3 short steps or reasons.` }));
    const ai = (out.questions || []).slice(0, aiCount);
    res.json({ questions: shuffle([...computed, ...ai]), computed: computed.length, aiChecked: !computed.length });
  } catch (err) {
    if (computed.length) return res.json({ questions: computed, computed: computed.length });
    res.status(502).json({ error: err.message });
  }
});

app.post("/api/skill", (req, res) => {
  const { lesson, score, of } = req.body || {};
  if (!(Number(of) > 0)) return res.status(400).json({ error: "bad score" });
  const all = readSkills();
  all[lesson] = all[lesson] || { checks: [] };
  all[lesson].checks.push({ at: new Date().toISOString(), score: Number(score), of: Number(of) });
  fs.writeFileSync(SKILLS, JSON.stringify(all, null, 2));
  res.json(all[lesson]);
});

// ── Step 9: score log ──
const SCORES = path.join(__dirname, "data", "scores.json");
const readScores = () => { try { return JSON.parse(fs.readFileSync(SCORES, "utf8")); } catch { return []; } };
app.get("/api/scores", (req, res) => res.json(readScores()));
app.post("/api/scores", (req, res) => {
  const { date, quiz, score, outOf } = req.body || {};
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date || "")) return res.status(400).json({ error: "Pick a date." });
  if (!(Number(outOf) > 0) || !(Number(score) >= 0) || Number(score) > Number(outOf)) return res.status(400).json({ error: "Score must be between 0 and the total." });
  const list = readScores();
  list.push({ id: Date.now().toString(36), date, quiz: String(quiz || "").slice(0, 80), score: Number(score), outOf: Number(outOf) });
  list.sort((a, b) => a.date.localeCompare(b.date));
  fs.writeFileSync(SCORES, JSON.stringify(list, null, 2));
  res.json(list);
});
app.delete("/api/scores/:id", (req, res) => {
  const list = readScores().filter((x) => x.id !== req.params.id);
  fs.writeFileSync(SCORES, JSON.stringify(list, null, 2));
  res.json(list);
});

// ── Today planner link ──
// Reads your Today planner (running on this laptop) for this course's next quiz
// and the matching slides from the class site. Nothing leaves the laptop.
const PLANNER_URL = process.env.PLANNER_URL || "http://127.0.0.1:8765/study";

function lessonNumbers(title) {
  // "Quiz 6 (10, 11)" -> [10, 11]; "Quiz 8 (14 - 16)" -> [14, 15, 16]
  const m = title.match(/\(([^)]*)\)/);
  if (!m) return [];
  const nums = [];
  for (const part of m[1].split(",")) {
    const r = part.match(/(\d+)\s*-\s*(\d+)/);
    if (r) { for (let n = +r[1]; n <= +r[2]; n++) nums.push(n); }
    else { const n = part.match(/\d+/); if (n) nums.push(+n[0]); }
  }
  return nums;
}

app.get("/api/planner", async (req, res) => {
  let data;
  try {
    const r = await fetch(PLANNER_URL);
    data = await r.json();
  } catch (err) {
    return res.status(503).json({ error: "Couldn't reach Today planner. Open the Today app, then refresh this page." });
  }
  const course = (data.courses || []).find((c) => c.key === COURSE_KEY);
  if (!course) return res.status(404).json({ error: `${COURSE.label} wasn't found in Today planner.` });
  const now = Date.now();
  const quizzes = (course.deadlines || [])
    .filter((d) => /^(quiz|exam)\b/i.test(d.title || "") && Date.parse(d.due) > now)
    .sort((a, b) => Date.parse(a.due) - Date.parse(b.due))
    .map((d) => {
      const lessons = /^quiz/i.test(d.title) ? lessonNumbers(d.title) : [];
      const slides = (course.materials || []).filter((m) =>
        lessons.some((n) => new RegExp("Lesson " + n + "\\b", "i").test(m.title || "")));
      return {
        title: d.title,
        due: d.due,
        lessons,
        gist: d.brief?.gist || "",
        slides: slides.map((m) => ({ title: m.title, url: m.url }))
      };
    });
  const homework = (course.deadlines || [])
    .filter((d) => /^(homework|hw)\b/i.test(d.title || "") && Date.parse(d.due) > now)
    .sort((a, b) => Date.parse(a.due) - Date.parse(b.due))
    .map((d) => ({ title: d.title, due: d.due, gist: d.brief?.gist || "" }));
  res.json({
    course: course.name, fetchedAt: data.fetchedAt, quizzes, homework,
    info: { code: course.code, instructor: course.instructor, meets: course.meets, ta: course.ta,
      officeHours: course.officeHours, attendance: course.attendance?.rule || "", grading: course.grading },
    grades: course.grades || null
  });
});

// Reload after code changes. Edits made from outside the Mac don't always reach
// the file watcher, so this lets the app restart itself; the start script relaunches it.
app.post("/api/restart", (req, res) => {
  if (!/^(::1|127\.0\.0\.1|::ffff:127\.0\.0\.1)$/.test(req.socket.remoteAddress || "")) return res.status(403).end();
  res.json({ restarting: true });
  setTimeout(() => process.exit(0), 200);
});
// Also restart by itself when server.js changes on disk (checked every 3s, works on any drive).
let _mtime = fs.statSync(__filename).mtimeMs;
setInterval(() => { try { const m = fs.statSync(__filename).mtimeMs; if (m !== _mtime) { console.log("server.js changed, restarting"); process.exit(0); } } catch {} }, 3000);

app.listen(PORT, () => {
  console.log(`Quiz Prep is running at http://localhost:${PORT}`);
});

