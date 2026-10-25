// Who uses this Quiz Prep and how each of their quiz courses works, from ~/.today/profile.json
// (TODAY_PROFILE overrides the path): profile.quizPrep.settings[courseKey]. Nothing about one course lives in the code.
const fs = require("fs");
const os = require("os");
const path = require("path");

const PROFILE_PATH = process.env.TODAY_PROFILE || path.join(os.homedir(), ".today", "profile.json");
const DEFAULT_CUTOFFS = { one: { "0.05": 1.65, "0.1": 1.28, "0.01": 2.33 }, two: { "0.05": 2, "0.1": 1.65, "0.01": 2.58 } };
const DEFAULT_LEVELS = { "90": 1.65, "95": 2, "99": 2.58 };

function loadProfile(file = PROFILE_PATH) {
  const base = { name: "you", school: "", lms: { kind: "", host: "" }, quizPrep: { courses: [], settings: {} } };
  try { return { ...base, ...JSON.parse(fs.readFileSync(file, "utf8")) }; } catch { return base; }
}

const esc = (x) => String(x).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

// One quiz course's settings over generic defaults. subject "stats" turns on the z-test calculator, number banks and cutoffs.
function courseSettings(profile, key) {
  const mine = ((profile.quizPrep || {}).settings || {})[key] || {};
  const s = { subject: "generic", title: key, professor: "", label: key, fileTag: "", lessonWord: "Lesson",
    noCalculator: false, quizPoints: 10, cutoffs: DEFAULT_CUTOFFS, levels: DEFAULT_LEVELS, ...mine };
  s.key = key;
  s.shortName = mine.shortName || s.title + (s.professor ? ` (${s.professor})` : "");
  s.practiceIntro = mine.practiceIntro || `a ${s.title} course`;
  s.paperLabel = mine.paperLabel || `${s.label} practice`;
  s.fileFilter = s.fileTag ? new RegExp(esc(s.fileTag), "i") : /./;
  s.filePattern = new RegExp(esc(s.lessonWord) + "\\s*(\\d+)", "i");
  return s;
}

const courseLine = (c) => c.title + (c.professor ? ` (${c.professor})` : "");

function cutoffText(c) {
  const t = c.cutoffs.two, o = c.cutoffs.one;
  return `Critical values for tests use the course table: two-tailed 0.05 -> ±${t["0.05"]}, 0.1 -> ±${t["0.1"]}, 0.01 -> ±${t["0.01"]}; one-tailed 0.05 -> ±${o["0.05"]}, 0.1 -> ±${o["0.1"]}, 0.01 -> ±${o["0.01"]}.`;
}

// "No calculator" rules: the full statistics version (perfect squares, table values, the course's cutoffs) or a short generic one.
function niceNumbers(c) {
  if (!c.noCalculator) return "";
  if (c.subject !== "stats") return "NO CALCULATOR on this quiz, so every number must work out cleanly by hand.\n- Every final answer is exact. Never write an answer that needed rounding.";
  return `NO CALCULATOR on this quiz, so every number must work out cleanly by hand, the way the professor writes them:
- Sample sizes are perfect squares (16, 25, 36, 49, 64, 81, 100, 144, 225, 256, 400, 900) so sqrt(n) is a whole number.
- sigma / sqrt(n) divides evenly (e.g. 45/9 = 5, 9/12 = 0.75, 15/10 = 1.5).
- For proportions, p(1-p) is a perfect square decimal (0.16 from 0.2*0.8, 0.09 from 0.1*0.9, 0.25 from 0.5*0.5, 0.0576 is NOT ok) and n is a perfect square, so sqrt(p(1-p)/n) is exact (0.4/16 = 0.025, 0.3/20 = 0.015).
- z-scores come out as whole numbers or halves: ±0.5, ±1, ±1.5, ±2, ±2.5, ±3.
- Probabilities come from the empirical rule or standard table values: 0.6826, 0.9544, 0.9974, 0.1587, 0.8413, 0.0228, 0.9772, 0.0013, 0.9987, 0.0668, 0.3085.
- ${cutoffText(c)}
- Every final answer is exact. Never write an answer that needed rounding (like 0.048 or 2.14).`;
}

// Checkers must use the professor's own cutoffs (±2, not ±1.96), or they flag right answers. Stats courses only.
const courseCutoffs = (c) => c.subject === "stats"
  ? "Use the course's critical values (the professor's table): " + cutoffText(c).replace(/^Critical values for tests use the course table: /, "") : "";

const lmsName = (p) => ({ brightspace: "Brightspace", canvas: "Canvas", moodle: "Moodle", blackboard: "Blackboard" })[(p.lms || {}).kind] || "your class site";

module.exports = { loadProfile, courseSettings, courseLine, cutoffText, niceNumbers, courseCutoffs, lmsName, DEFAULT_CUTOFFS, DEFAULT_LEVELS };
