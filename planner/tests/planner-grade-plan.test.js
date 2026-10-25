// Slices the grade plan out of planner.html and checks the projections in node.
const fs = require('fs'), path = require('path'), assert = require('assert');
const html = fs.readFileSync(path.join(__dirname, '..', 'planner.html'), 'utf8');
const a = html.indexOf('// ---- grade plan (pure)'), b = html.indexOf('// ---- end grade plan (pure)');
assert(a > 0 && b > a, 'grade plan section markers missing');
const api = new Function(html.slice(a, b) + '; return { gradeLeftCount, gradeCatFinish, gradeProject, gradeSolve };')();

const items = (name, scores, out) => scores.map((p, i) => ({ name: name + ' ' + (i + 1), points: p, outOf: out }));
// A made-up math class, as grades.py summarizes it: an Exam 1 scored 0 and reweighted to 10%
const math = { categories: [
  { name: 'Homework', weight: 0.05, pct: 95.39, drops: 2, outOf: 12,
    items: [{ name: 'Homework 1', points: 38.5, outOf: 45 }, { name: 'Homework 2', points: 30, outOf: 30 },
            { name: 'Homework 3', points: 30, outOf: 30 }, { name: 'Homework 4', points: 48, outOf: 50 }] },
  { name: 'Quizzes', weight: 0.20, pct: 80, drops: 3, outOf: 12, items: items('Quiz', [8, 8.5, 9, 5, 9.5], 10) },
  { name: 'Exam 1', weight: 0.10, pct: 0, drops: 0, outOf: null, items: [{ name: 'Exam 1 Curved Score', points: 0, outOf: 100 }] },
  { name: 'Exam 2', weight: 0.20, pct: null, drops: 0, outOf: null, items: [] },
  { name: 'Final Exam', weight: 0.45, pct: null, drops: 0, outOf: null, items: [] },
] };
const cat = n => math.categories.find(c => c.name === n);

// what's still to come: 8 homeworks, 7 quizzes, one of each exam, nothing on Exam 1
assert.deepStrictEqual(math.categories.map(api.gradeLeftCount), [8, 7, 0, 1, 1]);

// perfect quizzes from here: the 5/10 and 8/10 and 8.5/10 drop, so 88.5 of 90 kept
assert.ok(Math.abs(api.gradeCatFinish(cat('Quizzes'), 100) - 88.5 / 90 * 100) < 1e-9);
// 90% on the rest: best 9 of [95, 90, 85, 80, 50, 90 x7] = 95 + 90 x8
assert.ok(Math.abs(api.gradeCatFinish(cat('Quizzes'), 90) - (95 + 90 * 8) / 9) < 1e-9);
// homework drops the two lowest of twelve; the 85.6% on HW 1 goes first
assert.ok(Math.abs(api.gradeCatFinish(cat('Homework'), 100) - 100) < 1e-9);
// a posted exam stays put whatever the level, an unsat one is the level
assert.strictEqual(api.gradeCatFinish(cat('Exam 1'), 100), 0);
assert.strictEqual(api.gradeCatFinish(cat('Exam 2'), 73), 73);

// the most still possible: everything perfect, Exam 1 still 0
const top = api.gradeProject(math, null, 100);
assert.ok(Math.abs(top.total - (5 + 20 * 88.5 / 90 + 0 + 20 + 45)) < 1e-9, 'ceiling ' + top.total);
assert.strictEqual(top.parts.find(p => p.name === 'Exam 1').open, false);

// one score held on everything left that makes an 86: just under 96
const even = api.gradeSolve(math, 86);
assert.ok(even > 95.5 && even < 96, 'even level ' + even);
assert.ok(api.gradeProject(math, null, Math.ceil(even)).total >= 86);
assert.ok(api.gradeProject(math, null, Math.floor(even)).total < 86);

// named levels win over the fallback
const mine = { Homework: 95, Quizzes: 95, 'Exam 2': 95, 'Final Exam': 100 };
const p = api.gradeProject(math, mine, 0);
assert.ok(Math.abs(p.parts.find(x => x.name === 'Final Exam').points - 45) < 1e-9);
// 90s on quizzes and Exam 2 fall short of 86 even with a perfect final
assert.ok(api.gradeProject(math, Object.assign({}, mine, { Quizzes: 90, 'Exam 2': 90 }), 0).total < 86);

// solving one category with the rest held: what the final needs for an 86
const fin = api.gradeSolve(math, 86, mine, 'Final Exam');
assert.ok(fin > 96 && fin < 97, 'final needs ' + fin);
const held = Object.assign({}, mine, { 'Final Exam': fin });
assert.ok(Math.abs(api.gradeProject(math, held, 0).total - 86) < 1e-6);
// with weak quizzes the final alone can't carry it
assert.strictEqual(api.gradeSolve(math, 86, Object.assign({}, mine, { Quizzes: 60 }), 'Final Exam'), null);

// out of reach and already banked
assert.strictEqual(api.gradeSolve(math, 90), null);
assert.strictEqual(api.gradeSolve({ categories: [
  { name: 'Quizzes', weight: 0.9, pct: 95, drops: 0, outOf: null, items: [{ name: 'Quiz 1', points: 95, outOf: 100 }] },
  { name: 'Final', weight: 0.1, pct: null, drops: 0, outOf: null, items: [] }] }, 80), 0);

console.log('grade plan ok');
