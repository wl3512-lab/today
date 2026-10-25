// Slices the pure rollover section out of planner.html and checks it in node.
const fs = require('fs'), path = require('path'), assert = require('assert');
const html = fs.readFileSync(path.join(__dirname, '..', 'planner.html'), 'utf8');
const a = html.indexOf('// ---- rollover (pure)'), b = html.indexOf('// ---- end rollover (pure)');
assert(a > 0 && b > a, 'rollover section markers missing');
const api = new Function(html.slice(a, b) + '; return { carryOpenTasks, dayKeyTime };')();

function fresh() { return { studyTasks: [] }; }

// Halfway through an assignment at midnight: the open steps follow her to today,
// the ticked one stays on yesterday.
{
  const all = { '2026-9-18': { studyTasks: [
    { text: 'read the case (20m)', done: true, stepName: 'read the case', deadlineId: 'a1' },
    { text: 'outline (30m)', done: false, stepName: 'outline', deadlineId: 'a1' },
    { text: 'email GA about recordings', done: false },
  ] } };
  const today = fresh();
  assert.strictEqual(api.carryOpenTasks(all, '2026-9-19', today, {}), 2);
  assert.deepStrictEqual(today.studyTasks.map(t => t.text), ['outline (30m)', 'email GA about recordings']);
  assert.deepStrictEqual(all['2026-9-18'].studyTasks.map(t => t.text), ['read the case (20m)']);
}

// Skipped days: Friday's leftovers still arrive on Monday, oldest first, and
// nothing is carried twice.
{
  const all = {
    '2026-9-16': { studyTasks: [{ text: 'wiki week 3', done: false }] },
    '2026-9-18': { studyTasks: [{ text: 'sketch UI', done: false }] },
    '2026-9-22': { studyTasks: [{ text: 'not yet', done: false }] },   // the future is left alone
  };
  const today = fresh();
  assert.strictEqual(api.carryOpenTasks(all, '2026-9-21', today, {}), 2);
  assert.deepStrictEqual(today.studyTasks.map(t => t.text), ['wiki week 3', 'sketch UI']);
  assert.strictEqual(api.carryOpenTasks(all, '2026-9-21', today, {}), 0);
  assert.deepStrictEqual(all['2026-9-22'].studyTasks.map(t => t.text), ['not yet']);
}

// A step she ticked on the assignment page since is closed, not carried;
// duplicates (same ledger step or same text) are not added again.
{
  const all = { '2026-9-18': { studyTasks: [
    { text: 'outline (30m)', done: false, stepName: 'outline', deadlineId: 'a1' },
    { text: 'record part 2', done: false, ledgerId: 'L9' },
    { text: 'record part 3', done: false },
  ] } };
  const today = { studyTasks: [{ text: 'record part 2 again', done: false, ledgerId: 'L9' }, { text: 'record part 3', done: false }] };
  api.carryOpenTasks(all, '2026-9-19', today, { a1: ['outline'] });
  assert.deepStrictEqual(today.studyTasks.map(t => t.text), ['record part 2 again', 'record part 3']);
  assert.strictEqual(all['2026-9-18'].studyTasks[0].done, true);
  assert.strictEqual(all['2026-9-18'].studyTasks.length, 1);
}

// Keys that aren't days (older storage shapes) are ignored.
{
  const all = { junk: { studyTasks: [{ text: 'x', done: false }] }, '2026-9-18': {} };
  const today = fresh();
  assert.strictEqual(api.carryOpenTasks(all, '2026-9-19', today, {}), 0);
  assert.ok(Number.isNaN(api.dayKeyTime('junk')));
}
console.log('planner-rollover: ok');

// A session shows its own assignment's steps and what she typed, not last
// week's leftovers of the same class; those are counted as stale.
{
  const api2 = new Function(html.slice(a, b) + '; return { tasksFor };')();
  const tasks = [
    { text: 'Skim section 4 notes (20m)', done: false, courseKey: 'stat101' },            // HW2 leftover
    { text: 'Open schedule sheet (5m)', done: false, courseKey: 'stat101', deadlineId: 'hw3' },
    { text: 'how to make a project in xcode', done: true },                             // her own
    { text: 'Watch recording 1', done: false, courseKey: 'pop-culture' },           // other class
    { text: 'ask TA about q4', done: false, courseKey: 'stat101', ledgerId: 's_1' },       // her course step
  ];
  const v = api2.tasksFor(tasks, { courseKey: 'stat101', deadlineId: 'hw3', short: 'Math' });
  assert.deepStrictEqual(v.shown, [1, 2, 4]);
  assert.deepStrictEqual(v.stale, [0]);
  assert.deepStrictEqual(api2.tasksFor(tasks, null).shown, [0, 1, 2, 3, 4]);
}
console.log('ok tasksFor');
