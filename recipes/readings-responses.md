# Recipe: readings and weekly responses (humanities, writing, seminars)

**Fits:** a reading list, a short response or discussion post every week, papers a few times a term.

Do the generic recipe first, then:

## Ask
1. When is the weekly response due, and what does it have to be? (300 words, a discussion post, a reply to two classmates.)
2. Are there weeks off (breaks, paper weeks)?
3. Where is the reading list: the platform, a published Google Doc, the instructor's website?
4. Paper due dates and lengths.

## Write
- A `recurring` rule for the weekly response (`title`, `weekday`, `time`, `from`, `until`, `skip` for weeks off). Real deadlines from the platform win over the rule for any week they cover.
- Papers in `assignments.items` (`title`, `due`, `submitVia`) unless the platform already lists them.
- The reading list as a `gdoc` source (you get told when the doc changes) or a `site` source with its host in profile `publicHosts`.
- `briefNotes`: the response rules in the instructor's words, so the brief for each week says what a good one looks like.
- `kit.physical`: printed reading, highlighter.

## A class website with no feed
If the instructor's own site is the only place weekly work appears, Claude can write a small plugin: a Python module in `~/.today/plugins/` with `fetch_items(course, errors)` returning that course's deadlines (`title`, `due` as ISO time, `source`, `url`), named in profile `plugins`. It lives outside the repo, so updates never touch it. See `planner/plugins.py` for everything a plugin can offer.

## Check
- After a sync the next response shows on Today with its date, and the brief quotes the response rules.
