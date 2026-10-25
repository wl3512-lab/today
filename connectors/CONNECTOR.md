# Connector contract

Every school platform Today reads (Brightspace, Canvas, Campuswire, and any
connector Claude writes for a new one) speaks this contract. Brightspace was
the first; the others conform to it rather than the reverse.

The point: the OS layer merges, sorts, and renders items **without knowing
where they came from**. Source-specific knowledge stops at the connector
boundary.

## The Item

```json
{
  "id":      "brightspace:deadline:123456:789",
  "source":  "brightspace",
  "kind":    "deadline",
  "title":   "Problem Set 4",
  "body":    "Submit as a single PDF.",
  "url":     "https://brightspace.example.edu/d2l/lms/dropbox/...",
  "at":      "2026-09-10T03:59:00Z",
  "context": "General Chemistry",
  "status":  "open",
  "meta":    { "type": "assignment", "courseId": 123456 }
}
```

| field | rule |
|---|---|
| `id` | `<source>:<kind>:<scope>:<localId>`. Stable across syncs — this is what dedupes and diffs. Never derive it from a mutable field like the title. |
| `source` | connector name, lowercase |
| `kind` | `deadline` \| `message` \| `grade` \| `event` |
| `title` | one line, plain text, no markup |
| `body` | plain text, may be `""` |
| `url` | deep link back to the source, or `null` |
| `at` | ISO8601 **UTC**, `Z`-suffixed, or `null`. The one moment that matters. |
| `context` | course / calendar / thread name |
| `status` | `open` \| `done` \| `overdue` \| `null` |
| `meta` | source-specific passthrough. The OS never interprets this. |

`at` carries different meanings per kind, which is the whole trick — it lets
one sort put a due date and an unread email on the same timeline:

- `deadline` → when it is due
- `message` → when it arrived
- `event` → when it starts
- `grade` → when it was posted

## The envelope

```json
{
  "source": "brightspace",
  "fetchedAt": "2026-09-02T19:40:00Z",
  "stale": false,
  "items": [ ... ],
  "errors": [ { "context": "Some Course", "error": "HTTP_403 ..." } ]
}
```

`errors` is **partial failure, not total failure**. One course (or one Gmail
label) being inaccessible must still return everything else. A connector that
throws away good data because one sub-fetch failed is a broken connector.

`stale` tells the UI it is looking at cache so it can show an indicator
instead of silently lying about freshness.

## Cache-first, always

Brightspace costs a browser spawn and an SSO-backed round trip — far too slow
to sit in front of a UI paint. So:

```
bs feed --cached      # instant, never touches the network, may be stale
bs feed               # cache if younger than --max-age (default 900s), else refetch
bs feed --refresh     # force
bs sync               # refresh cache, print a summary
```

If a refetch fails but a cache exists, the cache is served with `stale: true`
rather than erroring. **Degrade, don't disappear.** Any connector talking to a
slow or flaky upstream should do the same, and the OS should render stale data
with a marker rather than an empty pane.

Cache lives at `~/.brightspace-cache.json`, written atomically via
temp-file + rename so a reader never catches a half-written file.

Suggested wiring: a background `bs sync` on a timer, with the UI reading
`--cached` exclusively. The UI then never blocks on Brightspace at all.

## Integration surface

`<cli> feed [--cached] [--max-age S]` prints the envelope on stdout and exits
non-zero only on a hard failure. `planner/study_sync.py` runs it and keys items
by `meta.courseId`, which must equal the course's `lmsId` in `~/.courses.json`.
A Python host can also load the CLI file and call `build_feed()` directly.

## Connectors in this folder

| folder | reads | sign-in |
|---|---|---|
| `brightspace/bs` | any school's Brightspace (D2L): assignments, quizzes, discussions, content, announcements, grades | `bs login` opens a browser window once; the school's address is `lms.host` in the profile |
| `canvas/canvas` | any school's Canvas: assignments (with submitted/graded state), modules, announcements, grades | `canvas login` saves a personal access token to `~/.today/canvas-token` |
| `campuswire/cw` | one class's Campuswire feed | `cw --group <id> login` opens a browser window once |

Discord is not shipped: reading it would mean automating a personal account,
which Discord's terms forbid. A course can still link its server.

## Adding a connector (Moodle, Blackboard, Schoology, ...)

Checklist for a new source:

- [ ] Emit the Item shape above, `at` normalized to UTC
- [ ] Stable `id` that survives a refetch
- [ ] `meta.courseId` on every course item, matching `lmsId` in the registry
- [ ] Partial failure lands in `errors`, never raises past the boundary
- [ ] Cache-first with an explicit `stale` flag (serve stale rather than nothing)
- [ ] `status` command reporting auth health, and a `login` that fixes it
- [ ] Tests on made-up API answers, like `tests/test_canvas.py`
- [ ] An entry in `LMS_CLI` at the top of `planner/study_sync.py`

Prefer an official API with a student token (Canvas and Moodle both have one).
Fall back to a logged-in browser session (how `bs` works) only when the school
gives students no token. Keep auth inside each connector and let only the Item
shape be shared.
