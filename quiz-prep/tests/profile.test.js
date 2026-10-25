const assert = require("assert");
const fs = require("fs");
const path = require("path");
const { loadProfile, courseSettings, courseLine, cutoffText, niceNumbers, courseCutoffs, lmsName } = require("../lib/profile");

// nobody's settings: a generic course, no stats-only rules
const none = loadProfile("/nonexistent/profile.json");
assert.strictEqual(none.name, "you");
const g = courseSettings(none, "chem101");
assert.strictEqual(g.subject, "generic");
assert.ok(g.fileFilter.test("anything.pdf"), "no file tag: every PDF counts");
assert.ok(g.filePattern.test("Lesson 4 - Stoichiometry"));
assert.strictEqual(courseLine(g), "chem101");
assert.strictEqual(niceNumbers(g), "", "no calculator rules unless the course has them");
assert.strictEqual(courseCutoffs(g), "", "cutoff tables only for stats courses");
assert.strictEqual(lmsName(none), "your class site");

// a statistics course without a calculator: the full rules, the professor's table, its own file names
const stat = courseSettings({ name: "Test Student", lms: { kind: "brightspace" }, quizPrep: { settings: { stat101: {
  subject: "stats", noCalculator: true, quizPoints: 10, fileTag: "stat101",
  title: "STAT 101, Introduction to Statistics", professor: "Prof. Lee",
  shortName: "STAT 101 (Prof. Lee)",
  practiceIntro: "an intro statistics course (STAT 101)",
  label: "STAT 101", paperLabel: "STAT 101 practice" } } } }, "stat101");
assert.strictEqual(courseLine(stat), "STAT 101, Introduction to Statistics (Prof. Lee)");
assert.strictEqual(cutoffText(stat), "Critical values for tests use the course table: two-tailed 0.05 -> ±2, 0.1 -> ±1.65, 0.01 -> ±2.58; one-tailed 0.05 -> ±1.65, 0.1 -> ±1.28, 0.01 -> ±2.33.");
assert.strictEqual(niceNumbers(stat), fs.readFileSync(path.join(__dirname, "fixtures", "old-nice-numbers.txt"), "utf8"));
assert.strictEqual(courseCutoffs(stat), "Use the course's critical values (the professor's table): two-tailed 0.05 -> ±2, 0.1 -> ±1.65, 0.01 -> ±2.58; one-tailed 0.05 -> ±1.65, 0.1 -> ±1.28, 0.01 -> ±2.33.");
assert.ok(stat.fileFilter.test("STAT101 Lesson 10 - Hypothesis Testing.pdf") && !stat.fileFilter.test("CHEM Lesson 1.pdf"));
assert.strictEqual(lmsName({ lms: { kind: "brightspace" } }), "Brightspace");

// a stats course with a different professor's table
const other = courseSettings({ quizPrep: { settings: { stat2: { subject: "stats", noCalculator: true, cutoffs: { two: { "0.05": 1.96, "0.1": 1.645, "0.01": 2.576 }, one: { "0.05": 1.645, "0.1": 1.282, "0.01": 2.326 } } } } } }, "stat2");
assert.ok(cutoffText(other).includes("two-tailed 0.05 -> ±1.96"));
console.log("profile ok");
