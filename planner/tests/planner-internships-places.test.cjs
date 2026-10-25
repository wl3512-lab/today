// The Internships page (from the agent's clone) tags and filters postings by the student's own places.
// PLANNER_FILE=<path> runs it inside another copy of the planner page.
const test = require('node:test');
const assert = require('node:assert/strict');
const boot = require('./helpers/jsdom-page.cjs');

const tick = (ms) => new Promise((r) => setTimeout(r, ms));
const POSTINGS = [
  { id: 'a', role: 'Lab Intern', company: 'Far Co', location_group: 'us', status: 'new', fit: 5 },
  { id: 'b', role: 'Design Intern', company: 'Home Co', location_group: 'home', status: 'new', fit: 3 },
  { id: 'c', role: 'Data Intern', company: 'Anywhere Co', location_group: 'remote_global', status: 'new', fit: 4 },
  { id: 'd', role: 'Field Intern', company: 'State Co', location_group: 'state', status: 'new', fit: 2 }
];

async function everyPosting(places) {
  const posted = [];
  const page = boot({
    file: process.env.PLANNER_FILE || undefined,
    fetch: (url, opts) => {
      const u = String(url);
      let body = {};
      if (u.endsWith('/internships') && opts && opts.method === 'POST') { posted.push(1); body = { postings: POSTINGS }; }
      else if (u.endsWith('/internships')) body = places ? { postings: POSTINGS, places } : { postings: POSTINGS };
      return Promise.resolve({ ok: true, json: () => Promise.resolve(body), text: () => Promise.resolve(JSON.stringify(body)) });
    }
  });
  await tick(1200);
  const tab = [...page.document.querySelectorAll('#jbNav button')].find((b) => /Every posting/.test(b.textContent));
  assert.ok(tab, 'the Every posting tab is there');
  tab.click();
  await tick(50);
  const pane = page.document.getElementById('jbPanes');
  return {
    page, posted,
    filter: () => [...pane.querySelectorAll('.jb-locpick option')].map((o) => o.textContent),
    tags: () => [...pane.querySelectorAll('.jb-loc')].map((t) => t.textContent + (t.classList.contains('pri') ? '*' : ''))
  };
}

test('the places from the profile name the tags and lead the filter, in their order', { timeout: 20000 }, async () => {
  const v = await everyPosting([{ group: 'home', label: 'Springfield' }, { group: 'state', label: 'Elsewhere in Ohio' }]);
  try {
    assert.deepEqual(v.filter(), ['Anywhere', 'Springfield', 'Elsewhere in Ohio', 'Remote', 'United States', 'Other']);
    // their places and remote-anywhere sort first (by fit within), the US after
    assert.deepEqual(v.tags(), ['Remote*', 'Springfield*', 'Elsewhere in Ohio*', 'US']);
  } finally { v.page.window.close(); }
});

test('an older planner without places: the postings\' own groups stand in', { timeout: 20000 }, async () => {
  const v = await everyPosting(null);
  try {
    assert.deepEqual(v.filter(), ['Anywhere', 'Home', 'State', 'Remote', 'United States', 'Other']);
    assert.deepEqual(v.tags(), ['Remote*', 'Home*', 'State*', 'US']);
  } finally { v.page.window.close(); }
});
