# Recipe: a studio, client or team project class

**Fits:** a semester project with a client or mentor, team meetings, milestones and decks instead of weekly homework.

Do the generic recipe first, then:

## Ask
1. The client or project, the team members and who leads.
2. Milestones with dates (kickoff, check-ins, midterm review, final presentation).
3. How many client or mentor meetings, and which are done.
4. Where the team talks (email, Discord, Slack) and where files live (Drive folder, Figma, deck links).

## Write
- `schedule`: every milestone as `{ "date": "2026-10-14", "what": "Midterm review with client" }`. The class page shows a timeline.
- `clientMeetings`: `{ "rounds": 4, "done": ["2026-09-20"], "planned": ["2026-10-18"] }`.
- `team`: `name`, `client`, `members`, `leader`. Leave out emails unless they ask for them.
- Sources for the shared folder (`gdrive`), deck (`slides`), design file (`figma`). These are links, grouped on the class page.
- `gmail.query` if the client or producer only ever emails, e.g. `"from:producer@example.com OR subject:\"Team Blue\""` (needs the `gws` CLI signed in to their mail).
- `briefNotes`: the deliverable format the client asked for.

## Check
- The class page shows the timeline with the next milestone, and the links open.
