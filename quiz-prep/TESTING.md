# Manual test checklist

| # | Do this | You should see |
|---|---------|----------------|
| 1 | Double-click Start Quiz Prep.command | Terminal says "Quiz Prep is running at http://localhost:3123"; Chrome opens it |
| 2 | Open http://localhost:3123/api/health | "baseUrlLoaded": true |
| 2b | Study Kit tab | A home page with two cards (This week's quiz, New lesson) and small links; nothing stacked under them |
| 2c | Click Review on the quiz card, then the browser Back | Only the Review shows, titled "Quiz N · Review", with "Next: Symbols & formulas →"; Back returns to the home page |
| 2d | New lesson card → Start | Recap of last week, then one chunk per screen with a diagram, worked example, 🧠 hook and quick check; ←/→ keys move; last step is a cheat sheet that prints |
| 2e | Rebuild on the lesson page | Worked examples say "✓ The app worked these numbers out itself"; z values match the slides |
| 2f | Click "Get me to 100% →" on the quiz card | The first unfinished step's page opens with a red-bordered guide bar ("Step N of 8"); I did this ✓ ticks it and opens the next step; all 8 = "You're ready for Quiz N 🎉" |
| 2g | Build settings → "Build a kit for" → a later quiz | A "Showing the Quiz N kit" note; its own lessons are ticked; unticking a confirmed lesson on the next quiz shows a warning before you rebuild |
| 3 | Study Kit tab (Today app open) | Next quiz, date, "in N days", topics; ✓ line if confirmed by slides |
| 4 | Click Build study kit | After ~20s: Review, Symbols & formulas, Flashcards, Worksheet, Practice test |
| 5 | Flashcards: press Space, then → | Card flips, then moves to card 2 |
| 6 | Worksheet: Show solutions, then Print | Solutions appear; print preview shows only the worksheet (inside Today, it opens in Chrome and the print dialog comes up there) |
| 6b | Mark some parts ✓ and ✗, then Make a new worksheet | Most problems tagged "🔁 Missed last time" and every kind of ✗ question comes back; two tagged "✓ Keeping it fresh"; "This sheet: …" line on top; Review and Flashcards unchanged |
| 6c | Show solutions on a fresh worksheet | Solutions are plain text (√, ×, no LaTeX); any answer the checker disagreed with has an orange "Double-check this one" |
| 7 | Upload Quiz: "Or use photos already in data/photos", then Extract quiz | 2 previews, then editable questions |
| 8 | Choose a PDF in the upload box | "Please upload a JPG or PNG." |
| 9 | Change a point value, Save profile | "Saved to data/profiles/....json"; file has your change |
| 10 | Practice Quiz: Generate | Same number of questions, types and points as the profile; checker note |
| 11 | Show answers | Each answer has a "Why:" line with the worked steps; flagged ones are orange |
| 12 | Score Log: add date + score, close Terminal, start again | Score and chart still there |
| 13 | Score Log: enter 12 out of 10 | Error: score must be between 0 and the total |
