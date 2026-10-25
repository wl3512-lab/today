// Ready % for a quiz = study steps finished out of 8. Doing all 8 is 100%; wrong worksheet answers don't lower it.
// Two steps tick themselves: flashcards once every card is known, the first worksheet once every part is marked.
// Loads in the page (window.Ready) and in Node for tests.
(function (root) {
  const READY_STEPS = [
    { id: "review", label: "Read the Review and say each recipe out loud", tab: "review" },
    { id: "symbols", label: "Cover the Symbols & formulas table and write them from memory", tab: "symbols" },
    { id: "cards1", label: "Flashcards until every card is marked known", tab: "cards" },
    { id: "ws1", label: "Do the worksheet by hand, then mark each part ✓ or ✗", tab: "sheet" },
    { id: "ws2", label: "Make a new worksheet and redo it", tab: "sheet" },
    { id: "missed", label: "Redo every part you marked ✗", tab: "sheet" },
    { id: "test", label: "Practice test, timed, no notes, no calculator", tab: "test" },
    { id: "cards2", label: "Night before: flashcards one more time", tab: "cards" }
  ];
  const sheetKeys = (w) => (w?.problems || []).flatMap((p) => (p.parts?.length ? p.parts.map((x) => "Problem " + p.number + " " + x.label) : ["Problem " + p.number]));

  function doneSteps(progress = {}, kit = {}) {
    const done = new Set(READY_STEPS.filter((s) => (progress.plan || {})[s.id]).map((s) => s.id));
    const cards = (kit.cards || []).length;
    if (cards && new Set(progress.known || []).size >= cards) done.add("cards1");
    const keys = sheetKeys(kit.worksheet), marks = progress.marks || {};
    if (keys.length && keys.every((k) => marks[k] === "right" || marks[k] === "wrong")) done.add("ws1");
    return done;
  }

  function readiness(progress, kit) {
    const done = doneSteps(progress, kit);
    return { done: done.size, total: READY_STEPS.length, pct: Math.round((100 * done.size) / READY_STEPS.length),
      next: READY_STEPS.find((s) => !done.has(s.id)) || null, doneIds: done };
  }

  const api = { READY_STEPS, doneSteps, readiness };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.Ready = api;
})(typeof window !== "undefined" ? window : globalThis);
