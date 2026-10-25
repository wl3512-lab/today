# Recipe: a coding class taught from GitHub

**Fits:** lecture notes, labs or homework in a GitHub repo or wiki; homework pushed to your own repo.

Do the generic recipe first, then:

## Ask
1. The class repo URL (and wiki, if assignments are wiki pages).
2. Does each week have its own file? Is there a week/date table in the README?
3. Do you push homework to your own repo? Which one?
4. Which apps do you code in?

## Write (pick what matches)
- Class repo: `{ "kind": "github", "url": "<repo>", "role": "lecture notes", "access": "public" }`. New and changed files show up as materials.
- Weekly files with a `## Homework` section and a README table `| 01 | 2026-09-04 |`: add `{ "kind": "github-weekly", "url": "<repo>" }`. Each week's homework becomes a deadline at the next class.
- Wiki with `Assignment-N` pages: `{ "kind": "github-wiki-assignments", "url": "<repo>/wiki" }`, plus `sessions` (dates and topics) and profile `githubWikiName` so your own submission is recognized.
- Your homework repo: `{ "kind": "github-mine", "url": "<your repo>" }`. Pushes count as progress.
- `kit.apps`: the editor ("Visual Studio Code", "Xcode").
- A `recurring` rule as a stand-in for weeks whose homework is not posted yet.

## Check
- After a sync: the class's latest repo changes appear on its page, and this week's homework shows as a deadline.
- GitHub allows 60 unauthenticated API calls an hour. With several repos, `gh auth login` (GitHub CLI) lifts that.
