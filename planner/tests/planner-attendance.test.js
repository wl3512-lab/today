// Slices the attendance section out of planner.html and checks the counting.
const fs = require('fs'), path = require('path'), assert = require('assert');
const html = fs.readFileSync(path.join(__dirname, '..', 'planner.html'), 'utf8');
const a = html.indexOf('// ---- attendance (pure)'), b = html.indexOf('// ---- end attendance (pure)');
assert(a > 0 && b > a, 'attendance section markers missing');
const api = new Function(html.slice(a, b) + '; return { absenceTally, lastMeetingDay };')();

const ladder = [{ at: 4, effect: 'B' }, { at: 5, effect: 'C' }, { at: 6, effect: 'D' }, { at: 7, effect: 'F' }];
const famous = { allowed: 3, countsFrom: '2026-09-15', excusedMatters: false, late: { per: 2 }, penalties: ladder };

// nothing logged: all three left, next penalty is the B cap at 4
let t = api.absenceTally(famous, []);
assert.deepStrictEqual([t.used, t.left, t.penaltyNow, t.penaltyNext.effect], [0, 3, null, 'B']);

// an add/drop-week miss is free; two lates make one absence; excused is ignored here
t = api.absenceTally(famous, [
  { date: '2026-09-10', kind: 'absent' },
  { date: '2026-09-17', kind: 'late' },
  { date: '2026-09-22', kind: 'late' },
  { date: '2026-09-24', kind: 'absent', excused: true },
]);
assert.deepStrictEqual([t.used, t.left, t.lates, t.fromLates, t.free.length], [2, 1, 2, 1, 1]);

// three more puts her past the limit: the B cap applies, C is next
t = api.absenceTally(famous, ['2026-09-29', '2026-10-01', '2026-10-06', '2026-10-08'].map(d => ({ date: d, kind: 'absent' })));
assert.deepStrictEqual([t.used, t.left, t.penaltyNow.effect, t.penaltyNext.effect], [4, -1, 'B', 'C']);

// where excused matters, an excused absence costs nothing; lates don't convert without a rule
const coding = { allowed: 2, excusedMatters: true, late: null, penalties: [] };
t = api.absenceTally(coding, [{ date: '2026-09-25', kind: 'absent', excused: true }, { date: '2026-10-02', kind: 'late' }]);
assert.deepStrictEqual([t.used, t.left, t.lates], [0, 2, 1]);

// no set limit: left is null, the count still adds up
t = api.absenceTally({ allowed: null, excusedMatters: true, penalties: [] }, [{ date: '2026-09-30', kind: 'absent' }]);
assert.deepStrictEqual([t.used, t.left], [1, null]);

// last meeting day: Tue 9/29 for a Tue/Thu class, Fri 9/25 for a Friday class
const tue = new Date(2026, 8, 29, 20);
assert.strictEqual(api.lastMeetingDay({ meets: { day: 'Tue/Thu' } }, tue), '2026-09-29');
assert.strictEqual(api.lastMeetingDay({ meets: { day: 'Friday' } }, tue), '2026-09-25');
assert.strictEqual(api.lastMeetingDay({ meets: { day: 'Wednesday' } }, tue), '2026-09-23');
console.log('attendance ok');
