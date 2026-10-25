// Diagrams for the New lesson page. The AI only picks a type and fills in numbers; these draw them,
// so a curve is always a real normal curve and the same colour always means the same thing:
// blue = sample statistic, navy = parameter, red pen = α / rejection, green = confidence / middle, amber = your test statistic.
// Pure string builders: the page inserts them, and tests load this file in Node.
(function (root) {
  const esc = (t) => String(t ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const num = (v) => typeof v === "number" && Number.isFinite(v);
  const fmt = (n) => {
    const r = Math.round(n * 10000) / 10000;
    return r === 0 ? "0" : (r < 0 ? "−" : "") + String(Math.abs(r));
  };
  const p1 = (n) => n.toFixed(1);

  // ── bell: standard normal on z ∈ [−4, 4] ──
  const BASE = 180, X0 = 260, PX = 60, PEAK = 140;
  const X = (z) => X0 + z * PX;
  const Y = (z) => BASE - Math.exp(-z * z / 2) * PEAK;
  const curve = (a, b) => {
    const pts = [];
    for (let z = a; z <= b + 1e-9; z += 0.05) pts.push("L" + p1(X(z)) + "," + p1(Y(z)));
    return pts;
  };
  const region = (a, b, cls) =>
    `<path class="${cls}" d="M${p1(X(a))},${BASE} ${curve(a, b).join(" ")} L${p1(X(b))},${BASE} Z"/>`;

  function bellSVG(d) {
    if (!d || !["left", "right", "both", "middle"].includes(d.shade) || !num(d.cut) || d.cut <= 0 || d.cut > 4) return "";
    const c = d.cut, mark = num(d.mark) && Math.abs(d.mark) <= 12 ? d.mark : null;
    // a z past ±4 (the toy cars' z = 5) sits at the edge with an arrow, so it is still on screen
    const pz = mark === null ? null : Math.max(-3.85, Math.min(3.85, mark)), off = mark !== null && Math.abs(mark) > 4;
    const xs = num(d.mean) && num(d.se) && d.se > 0 ? (z) => fmt(Math.round((d.mean + z * d.se) * 1000) / 1000) : null;
    const tails = d.shade === "left" ? [[-4, -c]] : d.shade === "right" ? [[c, 4]] : d.shade === "both" ? [[-4, -c], [c, 4]] : [];
    const cuts = d.shade === "left" ? [-c] : d.shade === "right" ? [c] : [-c, c];
    const out = [];
    out.push(...tails.map(([a, b]) => region(a, b, "dg-tail")));
    if (d.shade === "middle") out.push(region(-c, c, "dg-mid"));
    out.push(`<path class="dg-curve" d="M${p1(X(-4))},${p1(Y(-4))} ${curve(-4, 4).join(" ")}"/>`);
    out.push(`<line class="dg-axis" x1="20" y1="${BASE}" x2="500" y2="${BASE}"/>`);
    for (let z = -3; z <= 3; z++) {
      out.push(`<line class="dg-axis" x1="${X(z)}" y1="${BASE}" x2="${X(z)}" y2="${BASE + 5}"/>`);
      if ([...cuts, ...(pz !== null && xs ? [pz] : [])].every((k) => Math.abs(k - z) > 0.75)) {
        out.push(`<text class="dg-tick" x="${X(z)}" y="${BASE + 19}" text-anchor="middle">${fmt(z)}</text>`);
        if (xs && z === 0) out.push(`<text class="dg-tick" x="${X(0)}" y="${BASE + 35}" text-anchor="middle">${esc(xs(0))}</text>`);
      }
    }
    const cutCls = d.shade === "middle" ? "dg-cut mid" : "dg-cut";
    for (const k of cuts) {
      out.push(`<line class="${cutCls}" x1="${p1(X(k))}" y1="${BASE}" x2="${p1(X(k))}" y2="${p1(Y(k) - 8)}"/>`);
      out.push(`<text class="dg-cut-label${d.shade === "middle" ? " mid" : ""}" x="${p1(X(k))}" y="${BASE + 19}" text-anchor="middle">z = ${fmt(k)}</text>`);
      if (xs) out.push(`<text class="dg-tick" x="${p1(X(k))}" y="${BASE + 35}" text-anchor="middle">${esc(xs(k))}</text>`);
    }
    const label = esc(d.areaLabel || "");
    if (label && d.shade === "middle") out.push(`<text class="dg-area mid" x="${X0}" y="128" text-anchor="middle">${label}</text>`);
    if (label && tails.length) for (const k of cuts) {
      const side = k < 0 ? -1 : 1;
      out.push(`<text class="dg-area" x="${p1(X(k) + side * 14)}" y="${p1(Y(k) - 16)}" text-anchor="${side < 0 ? "end" : "start"}">${label}</text>`);
    }
    if (mark !== null) {
      const mx = Math.min(430, Math.max(90, X(pz)));
      const text = (d.markLabel || "z = " + fmt(mark)) + (off ? (mark > 0 ? " (off the chart →)" : " (← off the chart)") : "");
      out.push(`<line class="dg-mark" x1="${p1(X(pz))}" y1="${BASE}" x2="${p1(X(pz))}" y2="30"/>`);
      out.push(`<text class="dg-mark-label" x="${p1(mx)}" y="22" text-anchor="middle">${esc(text)}</text>`);
      if (xs) {   // where her sample landed, in real units and in z
        out.push(`<text class="dg-mark-label" x="${p1(X(pz))}" y="${BASE + 19}" text-anchor="middle">${fmt(mark)}</text>`);
        out.push(`<text class="dg-mark-label" x="${p1(X(pz))}" y="${BASE + 35}" text-anchor="middle">${esc(xs(mark))}</text>`);
      }
    }
    const what = d.shade === "middle" ? `middle between z = ±${fmt(c)} shaded` : `${d.shade === "both" ? "both tails" : d.shade + " tail"} beyond z = ${d.shade === "right" ? "" : "±"}${fmt(c)} shaded`;
    return `<svg class="dg dg-bell" viewBox="0 0 520 230" role="img" aria-label="${esc("Bell curve, " + what + (label ? ": " + d.areaLabel : "") + (mark !== null ? ". Marked " + (d.markLabel || "z = " + fmt(mark)) : ""))}">${out.join("")}</svg>`;
  }

  // ── interval: a confidence interval (or any ±) on a number line ──
  function intervalSVG(d) {
    if (!d || !num(d.center) || !num(d.margin) || d.margin <= 0) return "";
    const m = d.margin, mark = num(d.mark) && Math.abs(d.mark - d.center) <= 4 * m ? d.mark : null;
    let lo = d.center - 2 * m, hi = d.center + 2 * m;
    if (mark !== null) { lo = Math.min(lo, mark - 0.5 * m); hi = Math.max(hi, mark + 0.5 * m); }
    const V = (v) => 30 + ((v - lo) / (hi - lo)) * 460;
    const a = d.center - m, b = d.center + m, out = [];
    out.push(`<line class="dg-axis" x1="20" y1="78" x2="500" y2="78"/>`);
    out.push(`<rect class="dg-mid" x="${p1(V(a))}" y="70" width="${p1(V(b) - V(a))}" height="16" rx="8"/>`);
    for (const v of [a, b]) {
      out.push(`<line class="dg-axis" x1="${p1(V(v))}" y1="66" x2="${p1(V(v))}" y2="92"/>`);
      out.push(`<text class="dg-tick" x="${p1(V(v))}" y="110" text-anchor="middle">${fmt(v)}</text>`);
    }
    out.push(`<circle class="dg-stat" cx="${p1(V(d.center))}" cy="78" r="6"/>`);
    out.push(`<text class="dg-stat-label" x="${p1(V(d.center))}" y="58" text-anchor="middle">${esc(d.centerLabel || fmt(d.center))}</text>`);
    if (mark !== null) {
      const mx = Math.min(470, Math.max(50, V(mark)));
      out.push(`<line class="dg-param" x1="${p1(V(mark))}" y1="34" x2="${p1(V(mark))}" y2="96"/>`);
      out.push(`<text class="dg-param-label" x="${p1(mx)}" y="24" text-anchor="middle">${esc(d.markLabel || fmt(mark))}</text>`);
    }
    return `<svg class="dg dg-interval" viewBox="0 0 520 125" role="img" aria-label="${esc(`Interval from ${fmt(a)} to ${fmt(b)} around ${d.centerLabel || fmt(d.center)}` + (mark !== null ? `; ${d.markLabel || fmt(mark)} marked` : ""))}">${out.join("")}</svg>`;
  }

  // ── flow: steps of a method, as boxes with arrows ──
  function flowHTML(d) {
    const steps = (d?.steps || []).filter((s) => String(s || "").trim());
    if (steps.length < 2) return "";
    return `<ol class="dg dg-flow">${steps.map((s, i) => `<li><span class="dg-step-n">${i + 1}</span><span>${esc(s)}</span></li>`).join("")}</ol>`;
  }

  // ── formula: one big line, each symbol coloured by what it is, and a colour key of the labelled ones ──
  const ROLES = ["stat", "param", "spread", "size", "result", "op"];
  function formulaHTML(d) {
    const parts = (d?.parts || []).filter((p) => String(p?.text ?? "").trim())
      .map((p) => ({ ...p, role: ROLES.includes(p.role) ? p.role : p.label ? "param" : "op" }));
    if (parts.length < 2) return "";
    const line = parts.map((p) => `<span class="tok ${p.role === "op" ? "op" : "role-" + p.role}">${esc(p.text)}</span>`).join("");
    const key = parts.filter((p) => p.role !== "op" && String(p.label || "").trim())
      .map((p) => `<li class="role-${p.role}"><b>${esc(p.text)}</b> ${esc(p.label)}</li>`).join("");
    return `<div class="dg dg-formula"><p class="f-line">${line}</p>${key ? `<ul class="f-key">${key}</ul>` : ""}</div>`;
  }

  // ── compare: side-by-side columns (H₀ vs Hₐ, one- vs two-tailed…) ──
  function compareHTML(d) {
    const cols = (d?.columns || []).filter((c) => c && String(c.head || "").trim() && (c.items || []).length);
    if (cols.length < 2) return "";
    return `<div class="dg dg-compare" style="--cols:${cols.length}">${cols.map((c) =>
      `<section><h5>${esc(c.head)}</h5><ul>${c.items.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></section>`).join("")}</div>`;
  }

  function diagram(d) {
    if (!d || typeof d !== "object") return "";
    const draw = { bell: bellSVG, interval: intervalSVG, flow: flowHTML, formula: formulaHTML, compare: compareHTML }[d.type];
    return draw ? draw(d) : "";
  }

  const api = { diagram, bellSVG, intervalSVG, flowHTML, formulaHTML, compareHTML, fmt };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.Diagrams = api;
})(typeof window !== "undefined" ? window : globalThis);
