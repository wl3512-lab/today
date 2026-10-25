"""A course's running average, from the scores Brightspace already posts.

The Brightspace feed hands the planner one "grade" item per gradebook row:
category rows ("Homework", "Quizzes") that Brightspace has already averaged,
and single items ("Quiz 1", "Exam 1"). The registry gives each course a
`gradeScheme` copied from its syllabus - category weights and the letter
scale - and this turns the two into what she actually wants to know: her
average so far, as a percentage and a letter.

The average is over what has been graded. With homework (5%) and quizzes
(20%) in and no exams yet, 84.6% means 84.6% of those 25 points - it is not a
projection of the final grade, and `gradedWeight` says how much of the course
it covers so the page can say so.

Each category also carries its syllabus drop rule (`drops`, plus `outOf` when
the syllabus says how many there are - math drops the lowest 2 of 12
homeworks and 3 of 12 quizzes), and the summary carries the letter `scale`,
so the page can show the rules her average is worked out under.

`needs` answers "what do I need on what's left": for each letter, the
average she'd need across the ungraded categories (`left`) if the graded
ones stay where they are. Over 100 is out of reach, 0 or less is already
safe. `changes` passes through any weight changes agreed with the
instructor (date + text), since the syllabus no longer tells the whole story.
"""
import re

# Courant's scale, from the math syllabus: [100-93] A, (93-90] A-, ...
DEFAULT_SCALE = [["A", 93], ["A-", 90], ["B+", 87], ["B", 83], ["B-", 80],
                 ["C+", 75], ["C", 65], ["D", 50], ["F", 0]]


def _norm(name):
    return re.sub(r"\s+", " ", (name or "").strip().lower())


def _pct(item):
    try:
        pts, out = float(item.get("points")), float(item.get("outOf"))
    except (TypeError, ValueError):
        return None
    return pts / out * 100 if out > 0 else None


def letter(pct, scale=None):
    for name, floor in scale or DEFAULT_SCALE:
        if pct >= floor - 1e-9:
            return name
    return (scale or DEFAULT_SCALE)[-1][0]


def _category(name, rows, drops):
    """This category's percentage, and the single items that went into it.

    Brightspace's own category row wins: it already applies the instructor's
    drop rules. Without one, average the items named like it ("Quiz 3" for
    "Quizzes"), dropping the lowest `drops` once there are more than that.
    """
    key = _norm(name)
    # singular forms: homeworks -> homework, quizzes -> quiz, classes -> class
    stems = {key, re.sub(r"s$", "", key), re.sub(r"es$", "", key), re.sub(r"zes$", "", key)}
    own = [r for r in rows if _norm(r["name"]) == key]
    parts = [r for r in rows if _norm(r["name"]) != key
             and any(_norm(r["name"]).startswith(s + " ") for s in stems)]
    if own:
        return own[0]["pct"], parts
    if not parts:
        return None, []
    scores = sorted(p["pct"] for p in parts)
    if drops and len(scores) > drops:
        scores = scores[drops:]
    return sum(scores) / len(scores), parts


def summarize(items, scheme):
    """items: Brightspace grade items ({title, at, meta:{gradeItem, points, outOf}}).
    Returns None when the course has no scheme or nothing has been graded."""
    if not scheme or not scheme.get("weights"):
        return None
    rows = []
    for it in items:
        meta = it.get("meta") or {}
        pct = _pct(meta)
        if pct is None:
            continue
        rows.append({"name": meta.get("gradeItem") or it.get("title", ""), "pct": pct,
                     "points": meta.get("points"), "outOf": meta.get("outOf"), "at": it.get("at")})
    drops = scheme.get("drops") or {}
    totals = scheme.get("outOf") or {}
    cats, got, earned = [], 0.0, 0.0
    for name, weight in scheme["weights"].items():
        pct, parts = _category(name, rows, drops.get(name, 0))
        cats.append({"name": name, "weight": weight,
                     "pct": None if pct is None else round(pct, 2),
                     "items": [{"name": p["name"], "points": p["points"], "outOf": p["outOf"]}
                               for p in sorted(parts, key=lambda p: p["name"])],
                     "drops": drops.get(name, 0), "outOf": totals.get(name)})
        if pct is not None:
            got += weight
            earned += weight * pct
    if not got:
        return None
    avg = earned / got
    scale = scheme.get("scale") or DEFAULT_SCALE
    left = [c for c in cats if c["pct"] is None]
    rest = sum(c["weight"] for c in left)
    total = sum(scheme["weights"].values())
    needs = [{"letter": name, "floor": floor, "need": round((floor * total - earned) / rest, 1)}
             for name, floor in scale if floor > 0] if rest > 0 else []
    return {"average": round(avg, 2), "letter": letter(avg, scale),
            "gradedWeight": round(got, 4), "categories": cats,
            "updated": max((r["at"] for r in rows if r.get("at")), default=None),
            "scale": scale, "needs": needs, "left": [c["name"] for c in left],
            "changes": scheme.get("changes") or [],
            "source": scheme.get("source") or "Brightspace"}
