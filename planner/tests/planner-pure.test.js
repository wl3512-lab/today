// Slices the pure planner section out of planner.html and checks it in node.
const fs = require('fs'), path = require('path'), assert = require('assert');
const html = fs.readFileSync(path.join(__dirname, '..', 'planner.html'), 'utf8');
const a = html.indexOf('// ---- session planner (pure)'), b = html.indexOf('// ---- end session planner (pure)');
assert(a > 0 && b > a, 'planner section markers missing');
const src = html.slice(a, b);
const api = new Function(src + '; return { PLAN, freeHours, sessionsNeeded, placeSessions, planMeetsOn, busyHours, stepSessions };')();

const courses = [
  { key: 'stat101', meets: { day: 'Tue/Thu', start: '16:55', end: '18:10' } },
  { key: 'media', meets: { day: 'Wednesday', start: '15:30', end: '16:45' } },
  { key: 'coding', meets: { day: 'Friday', start: '09:00', end: '12:00' } },
];
// Her calendar is the only other source of blocked time now.
const busy = [
  { start: '2026-09-22T21:00:00-04:00', end: '2026-09-23T00:00:00-04:00', title: 'club' },      // Tue night
  { start: '2026-09-23T17:00:00-04:00', end: '2026-09-23T18:00:00-04:00', title: 'practice' },   // Wed 5-6pm
  { start: '2026-09-20T13:30:00-04:00', end: '2026-09-20T15:30:00-04:00', title: 'practice' },   // Sun
];
// Tue 2026-09-22: class 16:55–18:10 (+30 pad → 16:25–18:40) blocks 16,17,18; club from 21 (−15 pad → 20:45) blocks 20, 21
const tue = new Date(2026, 8, 22);
assert.deepStrictEqual(api.freeHours(courses, tue, busy), [10, 11, 12, 13, 14, 15, 19]);
// Wed 2026-09-23: a class 15:30–16:45 (15–17:15) + practice 17–18 (16:45–18:15) blocks 15,16,17 and the 18 slot it pads into
assert.deepStrictEqual(api.freeHours(courses, new Date(2026, 8, 23), busy), [10, 11, 12, 13, 14, 19, 20, 21]);
// Sun: practice 13:30–15:30 (13:15–15:45) blocks 13, 14, 15
assert.deepStrictEqual(api.freeHours(courses, new Date(2026, 8, 20), busy), [10, 11, 12, 16, 17, 18, 19, 20, 21]);
// No busy list at all: only classes block
assert.deepStrictEqual(api.freeHours(courses, new Date(2026, 8, 20)), [10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21]);
// busyHours is the per-day view the inline planner greys out
assert.deepStrictEqual(api.busyHours(busy, new Date(2026, 8, 23)), [[16.75, 18.25, 'practice']]);

assert.strictEqual(api.sessionsNeeded(0), 1);
assert.strictEqual(api.sessionsNeeded(2.2), 3);
assert.strictEqual(api.sessionsNeeded(40), 8);

const now = new Date(2026, 8, 21, 20, 10);           // Mon 8:10pm
// due Fri 1pm, so the − 2h boundary (11:00) sharpens to a last session at 10:00
const due = new Date(2026, 8, 25, 13);
const plan = api.placeSessions(courses, { due: due.toISOString(), priority: { remaining: 3 } }, now, busy);
assert(plan && plan.sessions.length === 3, 'three sessions');
assert.strictEqual(plan.tight, false);
assert.strictEqual(plan.needed, 3);
assert.strictEqual(plan.due, due.toISOString());
const days = plan.sessions.map(s => s.at.slice(0, 10));
assert.strictEqual(new Set(days).size, 3, 'one per day');
assert.strictEqual(plan.sessions[0].at, '2026-09-21T21:00');   // first free hour after now on Monday
assert(plan.sessions.every(s => s.at <= '2026-09-25T10:00'), 'all at or before due − 2h − session length');

// remaining == null falls back to the estimate (hours)
const hoursPlan = api.placeSessions(courses, { due: due.toISOString(), priority: { hours: 2.2 } }, now, busy);
assert(hoursPlan && hoursPlan.sessions.length === 3, 'remaining == null uses priority.hours: ' + JSON.stringify(hoursPlan));

// a startBy that carries the due time-of-day must never rewind start into
// the past: startBy Mon 23:59 (this same day) should not send the first
// session back to 10am Monday, which is already gone by 8:10pm.
const startByPlan = api.placeSessions(courses, {
  due: due.toISOString(),
  priority: { remaining: 1, startBy: new Date(2026, 8, 21, 23, 59).toISOString() }
}, now, busy);
assert(startByPlan && startByPlan.sessions.length === 1, 'startBy plan places a session');
assert(startByPlan.sessions[0].at >= '2026-09-21T21:00', 'startBy never rewinds start into the past: ' + startByPlan.sessions[0].at);

const tight = api.placeSessions(courses, { due: new Date(2026, 8, 22, 23).toISOString(), priority: { remaining: 3 } }, now, busy);
assert(tight && tight.tight === true && tight.sessions.length === 3, 'tight plan fills the last day');

assert.strictEqual(api.placeSessions(courses, { due: new Date(2026, 8, 21, 21).toISOString(), priority: { remaining: 1 } }, now, busy), null);
console.log('planner-pure: ok');

// tight plans never stack more than two sessions on one day, and same-day
// pairs stay at least 2h apart
{
  const soon = api.placeSessions(courses, { due: new Date(2026, 8, 22, 23).toISOString(), priority: { remaining: 6 } }, now, busy);
  const perDay = {};
  soon.sessions.forEach(s => { const d = s.at.slice(0, 10); perDay[d] = perDay[d] || []; perDay[d].push(new Date(s.at).getTime()); });
  assert(Object.values(perDay).every(times => times.length <= 2), 'at most two per day when tight: ' + JSON.stringify(perDay));
  Object.keys(perDay).forEach(function (d) {
    const times = perDay[d].slice().sort((a, b) => a - b);
    if (times.length === 2) assert(times[1] - times[0] >= 2 * 3600000, 'same-day sessions stay >=2h apart: ' + d);
  });
  assert.strictEqual(soon.needed, 6);
  console.log('planner-pure: tight cap ok');
}

// related materials: the weekly slides/notes for a homework, by the numbers in its title
{
  const ra = html.indexOf('// ---- related materials (pure)'), rb = html.indexOf('// ---- end related materials (pure)');
  assert(ra > 0 && rb > ra, 'related materials markers missing');
  const rel = new Function(html.slice(ra, rb) + '; return { relatedMaterials, titleNumbers };')();
  const math = { materials: [
    { module: 'Course Information', title: 'Course Schedule', url: 'u0' },
    { module: 'Unannotated Lecture Slides', title: 'STAT101 Lesson 2 - Conditional Probability', url: 'u2' },
    { module: 'Unannotated Lecture Slides', title: 'STAT101 Lesson 3 - Tree Diagrams', url: 'u3' },
    { module: 'Unannotated Lecture Slides', title: 'STAT101 Lesson 12 - Something', url: 'u12' },
    { module: 'Lesson Notes', title: 'Lesson 2 Part I Annotated', url: 'n2a' },
    { module: 'Lesson Notes', title: 'Lesson 2 Part II Annotated', url: 'n2b' },
    { module: 'Lesson Notes', title: 'Lesson 3 Annotated', url: 'n3' },
  ]};
  assert.deepStrictEqual(rel.titleNumbers('Quiz 2 (2, 3)'), [2, 3]);
  assert.deepStrictEqual(rel.titleNumbers('Homework 3 (6, 7)'), [6, 7]);   // not Lesson 3
  assert.deepStrictEqual(rel.titleNumbers('Week 05 homework: Local Data 1'), [5, 1]);
  assert.deepStrictEqual(rel.relatedMaterials(math, { title: 'Quiz 2 (2, 3)', url: 'sheet' }).map(m => m.url), ['u2', 'u3', 'n2a', 'n2b']);
  const ml = { materials: [
    { module: '01-introduction', title: 'README.md', url: 'g1' },
    { module: '02-transfer-learning', title: 'README.md', url: 'g2' },
    { module: '12-something', title: 'README.md', url: 'g12' },
  ]};
  assert.deepStrictEqual(rel.relatedMaterials(ml, { title: 'Assignment 2: Transfer Learning', url: 'wiki2' }), [{ title: '02-transfer-learning', url: 'g2' }]);
  const media = { materials: [
    { module: 'Class Lecture Materials, Week #2 - Sept 9', title: 'Class 2 case study', url: 'e2' },
    { module: 'Class Lecture Materials, Week #4 - Sept 23', title: 'Class 4', url: 'e4' },
    { module: 'Rubrics', title: 'Case Study Rubric', url: 'r' },
  ]};
  assert.deepStrictEqual(rel.relatedMaterials(media, { title: 'WEEK #4 - CASE STUDY PAPER', url: 'x' }).map(m => m.url), ['e4']);
  assert.deepStrictEqual(rel.relatedMaterials(media, { title: 'Post here after class on Sept 16', url: 'x' }), [], 'a date is not a week number');
  console.log('planner-pure: related materials ok');
}

// standing commitments plan themselves once inside the start window
{
  const sa = new Function(src + '; return { shouldAutoPlan };')();
  const math = { autoPlan: { quiz: 2 } };
  const quiz = (dueDaysAhead, startByDaysAhead) => ({
    due: new Date(now.getTime() + dueDaysAhead * 86400000).toISOString(),
    priority: { id: 'q', kind: 'quiz', startBy: new Date(now.getTime() + startByDaysAhead * 86400000).toISOString() }
  });
  assert.strictEqual(sa.shouldAutoPlan(math, quiz(4, -1), now, false), true, 'start-by passed → plan');
  assert.strictEqual(sa.shouldAutoPlan(math, quiz(6, 2), now, false), true, 'due within 8 days → plan');
  assert.strictEqual(sa.shouldAutoPlan(math, quiz(20, 16), now, false), false, 'far away → wait');
  assert.strictEqual(sa.shouldAutoPlan(math, quiz(4, -1), now, true), false, 'already planned');
  assert.strictEqual(sa.shouldAutoPlan(math, quiz(-1, -5), now, false), false, 'past due');
  assert.strictEqual(sa.shouldAutoPlan({ autoPlan: { quiz: 2 } }, { due: quiz(4, -1).due, priority: { id: 'h', kind: 'problemset', startBy: quiz(4, -1).priority.startBy } }, now, false), false, 'other kinds untouched');
  assert.strictEqual(sa.shouldAutoPlan({}, quiz(4, -1), now, false), false, 'course without autoPlan');
  console.log('planner-pure: auto plan ok');
}

// a homework that carries its own pieces opens exactly those
{
  const ra = html.indexOf('// ---- related materials (pure)'), rb = html.indexOf('// ---- end related materials (pure)');
  const rel = new Function(html.slice(ra, rb) + '; return { relatedMaterials };')();
  const d = { title: 'Response: Degas · Broke IRL · Bodyguards', url: 'site#week3', materials: [
    { title: 'Degas: A superfan at the opera', url: 'nyt', kind: 'read' },
    { title: 'Famous on the Internet, Broke IRL', url: 'pod', kind: 'listen' },
    { title: 'Hiring 50 bodyguards', url: 'yt', kind: 'watch' },
    { title: 'no link', url: null, kind: 'read' } ] };
  assert.deepStrictEqual(rel.relatedMaterials({ materials: [{ title: 'Lesson 3', url: 'x' }] }, d).map(m => m.url), ['nyt', 'pod', 'yt']);
  assert.strictEqual(rel.relatedMaterials({}, d)[1].title, 'listen: Famous on the Internet, Broke IRL');
  console.log('planner-pure: own materials ok');
}

// Steps from the brief size the sessions; ticked steps are skipped.
const brief = { gist: 'g', steps: [{ name: 'read the case', minutes: 45 }, { name: 'skim', minutes: 10 },
                                   { name: 'outline', minutes: 30 }, { name: 'write', minutes: 90 }] };
const stepPlan = api.placeSessions(courses, { due: due.toISOString(), priority: { remaining: 3 }, brief: brief }, now, busy);
assert(stepPlan, 'step plan exists');
// the 10-minute "skim" is too short to stand alone, so it joins the next step
assert.deepStrictEqual(stepPlan.sessions.map(s => [s.step, s.minutes]),
  [['read the case', 45], ['skim \u00b7 outline', 40], ['write', 90]]);
const donePlan = api.placeSessions(courses, { due: due.toISOString(), priority: { remaining: 3 }, brief: brief,
                                              stepsDone: ['read the case', 'skim'] }, now, busy);
assert.deepStrictEqual(donePlan.sessions.map(s => s.step), ['outline', 'write']);
// no brief: unchanged hour blocks, no step field
const plain = api.placeSessions(courses, { due: due.toISOString(), priority: { remaining: 2 } }, now, busy);
assert(plain.sessions.every(s => s.minutes === 60 && !('step' in s)), 'plain sessions stay 60 min');
console.log('planner-pure: steps ok');
