const assert = require("assert");
const { askPrompt } = require("../lib/ask");

const p = askPrompt({ question: "why is z = 5?", where: "Lesson 10 · Toy Cars", screen: "x".repeat(9000), slides: "SLIDES",
  history: Array.from({ length: 10 }, (_, i) => ({ who: i % 2 ? "bot" : "me", text: "turn " + i })), cutoffs: "CUTOFFS" });
assert.ok(p.includes("why is z = 5?") && p.includes("Lesson 10 · Toy Cars") && p.includes("SLIDES") && p.includes("CUTOFFS"));
assert.ok(!p.includes("x".repeat(6001)) && p.includes("x".repeat(6000)), "screen text capped at 6000 characters");
assert.ok(!p.includes("turn 3") && p.includes("turn 4") && p.includes("turn 9"), "only the last 6 messages");
assert.ok(/step by step/i.test(p), "asks for worked steps");
const bare = askPrompt({ question: "hi" });
assert.ok(bare.includes("hi") && !bare.includes("undefined"));
console.log("ask ok");
