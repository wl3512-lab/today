# Quiz Prep

A study app for one quiz course that runs only on this laptop (which course, and how it works, comes from ~/.today/profile.json).

## Start
Double-click **Start Quiz Prep.command** in this folder. Chrome opens http://localhost:3123.
Keep the Terminal window open while you study; closing it stops the app.
Needs: Node.js 20+ (nodejs.org) and the Today app open (for your quiz schedule).

## Every week
1. Download the newest annotated slides and worksheets from Brightspace into **Downloads**.
2. Open **Study Kit**. It shows the next quiz. If the professor's "Upcoming Assessments" slide names the topics, those win over the schedule sheet.
3. Click **Build study kit**: review, symbols & formulas, flashcards, a fresh worksheet, practice test.
4. Redo the worksheet (Rebuild for new numbers), then take one practice test.
5. After the real quiz, log your score in **Score Log**.

## Tabs
- **Study Kit**: weekly kit for the next quiz, saved in data/kits.
- **Upload Quiz**: photo of a past quiz -> AI reads it -> fix the text -> save the format (data/profiles).
- **Practice Quiz**: new quiz in that exact format, with a checked answer key (data/practice). Print button.
- **Score Log**: real quiz scores with a chart (data/scores.json).

## Settings (.env, never shared)
- AI_BASE_URL: the AI service (a Replicate-style proxy)
- AI_TOKEN: optional, raises the rate limit
- PORT: 3123
- PLANNER_URL: Today planner (default http://127.0.0.1:8765/study)
- MATERIALS_DIRS: where slides/worksheets live (default ~/Downloads)

## Limits
AI answers can be wrong. Flagged answers mean the checker disagreed; trust your slides.
Handwritten annotations on slides are images, so the app only reads the typed slide text.
