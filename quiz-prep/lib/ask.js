// The Ask chatbot's prompt: what she is looking at, the slides behind it, and the last few messages.
// Models on the class proxy get the arithmetic right only when they write the steps out, so it always asks for them.
function askPrompt({ question, where = "", screen = "", slides = "", history = [], cutoffs = "", name = "the student", course = "this course",
  noCalculator = false, style = "Answer short and plain (under 150 words unless they ask for more), one idea at a time, with a concrete example from their screen when it helps." }) {
  const chat = history.slice(-6).map((m) => (m.who === "bot" ? "You: " : name + ": ") + String(m.text || "").slice(0, 1500)).join("\n");
  return `You are ${name}'s study buddy for ${course}.${noCalculator ? " Quizzes are by hand, no calculator." : ""}
${style}
For ANY calculation, work it out step by step, one short line per step, then give the result. Use the slides' notation and the professor's cutoffs.
${cutoffs}
Write math as plain text (√, ×, ≥, x̄, p̂, σ, μ, α, H₀, Hₐ), never LaTeX. No markdown headings.
${where ? `\nSHE IS LOOKING AT: ${where}` : ""}${screen ? `\nWHAT IS ON HER SCREEN:\n${String(screen).slice(0, 6000)}` : ""}${slides ? `\nTHE LECTURE SLIDES FOR THIS (source of truth):\n${slides}` : ""}${chat ? `\nTHE CHAT SO FAR:\n${chat}` : ""}

${name} asks: ${question}`;
}

module.exports = { askPrompt };
