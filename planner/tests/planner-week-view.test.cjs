// The Week page can show seven days or three. Three is the same calendar at
// a size she can read from across the desk: fewer columns, taller hours.
const test = require('node:test');
const assert = require('node:assert/strict');
const boot = require('./helpers/jsdom-page.cjs');
const tick = (ms = 10) => new Promise(r => setTimeout(r, ms));

function at(daysFromToday, hour, minutes = 0) {
  const d = new Date(); d.setHours(0, 0, 0, 0);
  d.setDate(d.getDate() + daysFromToday); d.setHours(hour, minutes, 0, 0);
  return d;
}

function setup(seed) {
  const study = {
    courses: [],
    busy: [
      { start: at(0, 10).toISOString(), end: at(0, 11).toISOString(), title: 'Studio today' },
      { start: at(5, 12).toISOString(), end: at(5, 13).toISOString(), title: 'Five days out' },
    ],
    allDay: [],
  };
  const b = boot({ fetch: async (url) => {
    const u = String(url);
    const body = u.endsWith('/study') ? study : u.endsWith('/ledger') ? { plans: {}, tasks: {} } : {};
    return { ok: true, json: async () => body, text: async () => JSON.stringify(body) };
  } });
  // build() runs after the fetches resolve, so storage seeded now is what it reads
  if (seed) b.window.localStorage.setItem('planner-week-span', seed);
  return b;
}

async function openWeek(b) {
  await tick(30);
  const btn = b.document.querySelector('.page-btn.week-btn');
  assert.ok(btn, 'Week button exists');
  btn.click();
  await tick();
  return b.document.getElementById('weekPage');
}

const columns = page => page.querySelectorAll('.wk-grid .wk-lines').length;
const block = (page, title) => [...page.querySelectorAll('.wk-block')].find(x => x.textContent.includes(title));
const headDates = page => [...page.querySelectorAll('.wk-colhead b')].map(x => Number(x.textContent));

test('opens on seven days with a Week / 3 days switch', async () => {
  const b = setup();
  try {
  const page = await openWeek(b);
  assert.deepEqual(b.errors, []);
  assert.equal(columns(page), 7);
  const opts = [...page.querySelectorAll('.wk-span button')];
  assert.deepEqual(opts.map(o => o.textContent), ['Week', '3 days']);
  assert.deepEqual(opts.map(o => o.getAttribute('aria-pressed')), ['true', 'false']);
  assert.ok(block(page, 'Five days out'), 'day five is on the week');
  assert.equal(block(page, 'Studio today').style.height, '44px');   // 46px hour
  } finally { b.window.close(); }
});

test('3 days shows today and the next two, enlarged', async () => {
  const b = setup();
  try {
  const page = await openWeek(b);
  const three = [...page.querySelectorAll('.wk-span button')][1];
  three.click();
  await tick();
  assert.equal(columns(page), 3);
  assert.equal(three.getAttribute('aria-pressed'), 'true');
  const grid = page.querySelector('.wk-grid');
  assert.ok(grid.classList.contains('wk-3day'));
  assert.equal(grid.style.getPropertyValue('--wk-days'), '3');
  const hour = parseFloat(grid.style.getPropertyValue('--wk-hour'));
  assert.ok(hour >= 70, 'hours are taller than the week\'s 46px, got ' + hour);
  // a one-hour event fills one of the taller hours
  assert.equal(block(page, 'Studio today').style.height, (hour - 2) + 'px');
  assert.equal(block(page, 'Five days out'), undefined, 'day five is not in the first three');
  const first = at(0, 0).getDate();
  assert.equal(headDates(page)[0], first);
  assert.equal(b.window.localStorage.getItem('planner-week-span'), '3');
  } finally { b.window.close(); }
});

test('in 3 days, the arrows step three days and the labels say so', async () => {
  const b = setup('3');
  try {
  const page = await openWeek(b);
  assert.equal(columns(page), 3, 'the saved choice is restored');
  const [prev, today, next] = page.querySelectorAll('.wk-nav button');
  assert.equal(next.getAttribute('aria-label'), 'Next 3 days');
  next.click();
  await tick();
  assert.equal(headDates(page)[0], at(3, 0).getDate());
  assert.ok(block(page, 'Five days out'), 'day five is in the second three');
  today.click();
  await tick();
  assert.equal(headDates(page)[0], at(0, 0).getDate());
  assert.equal(prev.getAttribute('aria-label'), 'Previous 3 days');
  } finally { b.window.close(); }
});

test('switching back to Week keeps the date she was looking at in view', async () => {
  const b = setup('3');
  try {
  const page = await openWeek(b);
  page.querySelectorAll('.wk-nav button')[2].click();   // days 3-5
  await tick();
  page.querySelectorAll('.wk-span button')[0].click();   // back to Week
  await tick();
  assert.equal(columns(page), 7);
  const dates = headDates(page);
  assert.ok(dates.includes(at(3, 0).getDate()), 'day three is still on screen: ' + dates);
  assert.equal(page.querySelectorAll('.wk-nav button')[2].getAttribute('aria-label'), 'Next week');
  } finally { b.window.close(); }
});

// An hour before now sits at the top of the grid, so the rest of today is
// in view instead of 07:00. Only when today is on screen, and only on
// opening, switching or pressing Today - never on a save, which re-renders.
function nowTop(hour) {
  const n = new Date();
  return Math.max(0, (n.getHours() + n.getMinutes() / 60 - 7 - 1) * hour);
}
const near = (a, b, hour) => Math.abs(a - b) <= hour / 20;   // a few minutes of drift

test('the grid opens scrolled to an hour before now, at either size', async () => {
  const b = setup();
  try {
    const page = await openWeek(b);
    const grid = page.querySelector('.wk-grid');
    assert.ok(near(grid.scrollTop, nowTop(46), 46), grid.scrollTop + ' vs ' + nowTop(46));
    page.querySelectorAll('.wk-span button')[1].click();
    await tick();
    assert.ok(near(grid.scrollTop, nowTop(72), 72), grid.scrollTop + ' vs ' + nowTop(72));
  } finally { b.window.close(); }
});

test('paging away keeps the scroll; Today brings it back to now', async () => {
  const b = setup('3');
  try {
    const page = await openWeek(b);
    const grid = page.querySelector('.wk-grid');
    const [, today, next] = page.querySelectorAll('.wk-nav button');
    grid.scrollTop = 5;
    next.click();
    await tick();
    assert.equal(grid.scrollTop, 5);
    today.click();
    await tick();
    assert.ok(near(grid.scrollTop, nowTop(72), 72), grid.scrollTop + ' vs ' + nowTop(72));
  } finally { b.window.close(); }
});
