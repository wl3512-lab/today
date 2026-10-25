// The AI sometimes writes LaTeX ("\( \sqrt{n} \)") even when asked not to; the page shows text, so turn it into √(n).
const SYMBOLS = { times: "×", cdot: "·", geq: "≥", ge: "≥", leq: "≤", le: "≤", approx: "≈", neq: "≠", pm: "±",
  mu: "μ", sigma: "σ", alpha: "α", beta: "β", theta: "θ", lambda: "λ", rho: "ρ", infty: "∞", to: "→", rightarrow: "→" };
const SUBS = { 0: "₀", 1: "₁", 2: "₂", a: "ₐ" };

function plainMath(s) {
  let t = String(s ?? "");
  for (let i = 0; i < 3; i++) {   // a few passes for nesting like \frac{\sigma}{\sqrt{n}}
    t = t.replace(/\\frac\{([^{}]*)\}\{([^{}]*)\}/g, "$1/$2")
      .replace(/\\sqrt\{([^{}]*)\}/g, "√($1)")
      .replace(/\\hat\{([^{}]*)\}/g, "$1̂")
      .replace(/\\bar\{([^{}]*)\}/g, "$1̄")
      .replace(/\\(?:text|mathrm|mathbf)\{([^{}]*)\}/g, "$1");
  }
  return t
    .replace(/\\[()[\]]/g, "")
    .replace(/\\left|\\right/g, "")
    .replace(/\\([a-zA-Z]+)/g, (m, w) => SYMBOLS[w] ?? m)
    .replace(/_\{?([012a])\}?/g, (m, c) => SUBS[c])
    .replace(/\\[,;!% ]/g, (m) => (m === "\\%" ? "%" : " "))
    .replace(/[ \t]{2,}/g, " ")
    .replace(/ ([.,;:])/g, "$1")
    .trim();
}

// Checkers sometimes say "disagree" and then give the same value, or the right value under another letter.
const norm = (s) => plainMath(s).toLowerCase().replace(/^[a-d]\)\s*/, "").replace(/[−–]/g, "-").replace(/[\s.,;:]+$/g, "").replace(/\s+/g, "");
function sameAnswer(mine, given) {
  const a = norm(mine), g = norm(given);
  return !!g && (a === g || (g.length >= 2 && a.includes(g)));
}

module.exports = { plainMath, sameAnswer };
