// The sidebar's Study Kit button opens the kit from any page, without switching pages.
// PLANNER_FILE=<path> checks another copy of the page (an older install) with the same test.
const test = require('node:test');
const assert = require('node:assert/strict');
const boot = require('./helpers/jsdom-page.cjs');

const tick = (ms) => new Promise((r) => setTimeout(r, ms));

test('sidebar Study Kit opens the kit overlay and leaves the page alone', { timeout: 15000 }, async () => {
  const calls = [];
  const { document, window } = boot({
    file: process.env.PLANNER_FILE || undefined,
    fetch: (url) => { calls.push(String(url)); return Promise.resolve({ ok: true, json: () => Promise.resolve({ ok: true }), text: () => Promise.resolve('{}') }); }
  });
  try {
  await tick(50);
  const btn = document.getElementById('railStudyKit');
  assert.ok(btn, 'there is a Study Kit button in the sidebar');
  assert.equal(btn.textContent.trim(), 'Study Kit');
  const before = document.querySelector('.page.active').getAttribute('data-page');
  btn.click();
  await tick(50);
  const overlay = document.querySelector('.qp-overlay');
  assert.ok(overlay && !overlay.hidden, 'the Study Kit overlay is open');
  assert.match(overlay.querySelector('iframe').src, /localhost:3123/);
  assert.ok(calls.some((u) => u.includes('3123/api/health')), 'it checks Quiz Prep is up first');
  assert.equal(document.querySelector('.page.active').getAttribute('data-page'), before, 'the page underneath did not change');
  assert.ok(!btn.classList.contains('active'), 'it never shows as the current page');
  } finally { window.close(); }
});
