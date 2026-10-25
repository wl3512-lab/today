# Recipe: any class (the base every other recipe builds on)

**Fits:** every class. Use it alone when the class has nothing special.

## Ask
1. Full name, short name for a tab, catalog code.
2. When it meets: day(s), start and end time, room. (For two meetings a week, use the first in `meets` and add the other as a `recurring` rule or a note.)
3. Instructor, TA, office hours.
4. Where homework is posted and turned in: the school platform, a class website, GitHub, email, paper?
5. "Can you drop the syllabus here?" A PDF or link is the fastest way to everything below.

## From the syllabus, fill in
- `grading` (weights as decimals that add to 1) and `gradeScheme` if there are drops or a letter scale.
- `attendance`: how many absences, whether excused ones count, lateness rule, what happens past the limit. Copy the rule in plain words into `rule` and `over`.
- `recurring` for any "due every Monday at 11:59pm" sentence.
- `assignments.items` for work listed only in the syllabus with dates.
- `briefNotes`: anything about *how* work should be done (format, length, citation style, "show your work").

## Platform link
- If the class is on the platform, find its id: open the class in a browser and copy the number from the URL (`/d2l/home/123456` on Brightspace, `/courses/123456` on Canvas). Put it in `lmsId` and add a source `{ "kind": "<brightspace|canvas>", "url": null, "role": "assignments + grades", "access": "session" }`.
- After the first sync, platform classes missing from `courses.json` show up with a "Not in your course registry" warning. Add them or put them in `ignore`.

## Study Kit
- `kit.apps`: apps opened when they press start (exact macOS app names: "Visual Studio Code", "Xcode", "Figma").
- `kit.physical`: the things to have on the desk (calculator, printed reading, water). Default is a short generic list.

## Check
- Run the sync once (see CLAUDE-SETUP.md) and confirm the class appears with its next deadline, meeting time and links.
