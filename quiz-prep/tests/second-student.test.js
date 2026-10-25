const assert = require("assert");
const path = require("path");
const { loadProfile, courseSettings, courseLine, niceNumbers, courseCutoffs, lmsName } = require("../lib/profile");
const { askPrompt } = require("../lib/ask");

// Sam: chemistry at State U on Canvas. No statistics tables, no calculator rules, nothing of this Mac's owner.
const sam = loadProfile(path.join(__dirname, "..", "..", "planner", "tests", "fixtures", "sam-profile.json"));
const chem = courseSettings(sam, "chem101");
assert.strictEqual(chem.subject, "chem");
assert.strictEqual(courseLine(chem), "CHEM 101, General Chemistry (Dr. Okafor)");
assert.strictEqual(niceNumbers(chem), "");
assert.strictEqual(courseCutoffs(chem), "");
assert.strictEqual(lmsName(sam), "Canvas");
assert.ok(chem.filePattern.test("CHEM101 Chapter 3 - Moles.pdf") && chem.fileFilter.test("CHEM101 Chapter 3 - Moles.pdf"));
assert.ok(!chem.fileFilter.test("STAT101 Lesson 10 - Hypothesis Testing.pdf"));
const p = askPrompt({ question: "why moles?", name: sam.name, course: courseLine(chem), noCalculator: chem.noCalculator });
const owner = loadProfile();   // this Mac's own settings, if any
const marks = [owner.name, owner.fullName, owner.chatStyle, ...Object.values((owner.quizPrep || {}).settings || {}).flatMap((c) => [c.title, c.professor, c.label])]
  .filter((w) => w && w.length > 3 && w !== "you");
for (const mark of [...marks, "no calculator"]) assert.ok(!p.includes(mark), mark + " leaked");
assert.ok(p.startsWith("You are Sam's study buddy for CHEM 101, General Chemistry (Dr. Okafor)."));
console.log("second student ok");
