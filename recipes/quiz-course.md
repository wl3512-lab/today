# Recipe: a class with weekly quizzes or exams (math, stats, science, econ)

**Fits:** regular quizzes or exams drawn from lecture slides and worksheets. Turns on **Quiz Prep**: a study kit per quiz (review, formulas, flashcards, a fresh worksheet, a practice test), photo-to-practice for past quizzes, and a score log.

Do the generic recipe first, then:

## Ask
1. When are quizzes? (A schedule sheet, the platform, or "every Friday in recitation".)
2. Are quizzes and exams taken without a calculator? (Then practice numbers are kept clean, the way a professor picks them.)
3. Where do the slides and worksheets come from, and what are the files called? (For example `CHEM101 Chapter 4 annotated.pdf`.) Quiz Prep reads them from Downloads by default.
4. Is it statistics with z-tests or confidence intervals? If yes, what critical values does the professor use (some use ±2, not ±1.96)?
5. Do quiz numbers match lesson numbers? (In some courses "Quiz 7" covers Lessons 9 and 10. Write down the mapping.)
6. Should study sessions plan themselves before each quiz? (Then `autoPlan: { "quiz": 2 }`, two sessions.)

## Write
- profile `quizPrep.courses`: add the course key.
- profile `quizPrep.settings.<key>`: `title`, `professor`, `label`, `fileTag` (a piece of text every slide file name has), `lessonWord` (`Lesson`, `Chapter`, `Week`), `noCalculator`, `quizPoints`, and `subject: "stats"` with `cutoffs` / `levels` only for statistics.
- course `autoPlan` if they said yes.
- A schedule sheet published as CSV becomes a `gsheet-csv` source if it uses the `14-Sep` / "Quiz 3" layout; otherwise put quiz dates in `assignments.items`.

## AI
Quiz Prep uses the student's own Claude Code (`claude -p`). If the school gives a class AI proxy, put it in `quiz-prep/.env` as `AI_BASE_URL`. The rule either way: the AI copies numbers off the slides and writes the words; `lib/calc.js` computes every answer.

## Check
- Open Quiz Prep from the planner's Study Kit, choose the next quiz and press **Build study kit** with one real slide file in Downloads.
