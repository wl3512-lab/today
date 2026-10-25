// What she marked on the last worksheet, and how the next one splits its problems.
// Keys match the page's mark buttons: "Problem 3 b" for a part, "Problem 3" for a problem without parts.
function markedParts(worksheet, marks = {}) {
  const missed = [], right = [];
  for (const p of worksheet?.problems || []) {
    for (const x of p.parts?.length ? p.parts : [{ label: "", text: "" }]) {
      const key = "Problem " + p.number + (x.label ? " " + x.label : "");
      const text = (p.text + " " + (x.text || "")).trim();
      if (marks[key] === "wrong") missed.push(text);
      if (marks[key] === "right") right.push(text);
    }
  }
  return { missed, right };
}

// Most problems go to what she missed (a single miss still gets two tries), two keep what she got right fresh,
// the rest cover topics the last sheet didn't test. null = no marks, write the sheet as usual.
function focusPlan(missedCount, rightCount, total = 6) {
  if (!missedCount && !rightCount) return null;
  const missed = missedCount ? Math.min(4, Math.max(2, missedCount)) : 0;
  const kept = rightCount ? Math.min(2, total - missed) : 0;
  return { missed, kept, fresh: total - missed - kept };
}

// How far a written sheet is from the planned mix (0 = right). The AI tends to even it out to 3/3.
function mixOff(problems, plan) {
  if (!plan) return 0;
  const n = (f) => (problems || []).filter((p) => p.focus === f).length;
  return Math.abs(n("missed") - plan.missed) + Math.abs(n("kept") - plan.kept);
}

module.exports = { markedParts, focusPlan, mixOff };
