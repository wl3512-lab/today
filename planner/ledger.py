"""The study ledger: what was worked on, for how long, and the steps she has
attached to each class. Unlike the study cache this is hers and permanent -
the sync never touches it - and unlike the per-day planner state it is one
file across days, because "hours on Week 03 homework" spans a week."""
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone

LEDGER = os.path.expanduser("~/.study-ledger.json")


def _now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _empty():
    return {"sessions": [], "steps": {}, "notes": {}, "plans": {}, "calEvents": {}, "tasks": {},
            "absences": {}}


def load(path=LEDGER):
    if not os.path.exists(path):
        return _empty()
    try:
        with open(path) as f:
            data = json.load(f)
    except OSError as exc:
        sys.stderr.write("[ledger] could not read %s: %s\n" % (path, exc))
        return _empty()
    except ValueError:
        # Never overwrite something we could not parse: park it next door so
        # a bad write costs a rename, not a semester of logged hours.
        parked = "%s.corrupt-%d" % (path, int(time.time()))
        try:
            os.replace(path, parked)
        except OSError as exc:
            sys.stderr.write("[ledger] unreadable %s and could not set it aside: %s\n" % (path, exc))
        return _empty()
    if not isinstance(data, dict):
        return _empty()
    out = _empty()
    if isinstance(data.get("sessions"), list):
        out["sessions"] = data["sessions"]
    if isinstance(data.get("steps"), dict):
        out["steps"] = data["steps"]
    if isinstance(data.get("notes"), dict):
        out["notes"] = data["notes"]
    if isinstance(data.get("plans"), dict):
        out["plans"] = data["plans"]
    if isinstance(data.get("calEvents"), dict):
        out["calEvents"] = data["calEvents"]
    if isinstance(data.get("tasks"), dict):
        out["tasks"] = data["tasks"]
    if isinstance(data.get("absences"), dict):
        out["absences"] = data["absences"]
    return out


def save(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=1)
    os.replace(tmp, path)
    return data


def apply_op(data, op):
    """One of {addSession}, {addStep}, {doneStep}, {removeSession}, {setNote},
    {setPlan}, {clearPlan}, {addTask}, {removeTask}, {addAbsence},
    {removeAbsence}, {setAbsence}. Anything else is a no-op.

    A task is her own work with no deadline, made on the week. Its id is
    used as a deadlineId, so it is planned and sent to the calendar exactly
    like homework; removing it removes its plan too."""
    if "addSession" in op:
        s = op["addSession"] or {}
        try:
            minutes = int(round(float(s.get("minutes", 0))))
        except (TypeError, ValueError, OverflowError):
            minutes = 0
        if minutes > 0:
            row = {
                "at": s.get("at") or _now_iso(),
                "minutes": minutes,
                "courseKey": s.get("courseKey") or None,
                "deadlineId": s.get("deadlineId") or None,
                "sid": s.get("sid") or None,
            }
            # menubar sessions say what kind they were and what she did;
            # planner sessions carry neither, so they stay as they were
            for key in ("kind", "note"):
                val = str(s.get(key) or "").strip()[:120]
                if val:
                    row[key] = val
            data["sessions"].append(row)
    elif "removeSession" in op:
        sid = op["removeSession"]
        data["sessions"] = [x for x in data["sessions"] if not (sid and x.get("sid") == sid)]
    elif "setNote" in op:
        n = op["setNote"] or {}
        did = (n.get("deadlineId") or "").strip()
        text = (n.get("text") or "").strip()
        if did:
            if text:
                data.setdefault("notes", {})[did] = {"text": text, "at": _now_iso()}
            else:
                data.setdefault("notes", {}).pop(did, None)
    elif "addStep" in op:
        s = op["addStep"] or {}
        key = (s.get("courseKey") or "").strip()
        text = (s.get("text") or "").strip()
        if key and text:
            data["steps"].setdefault(key, []).append({
                "id": "s_" + uuid.uuid4().hex[:10],
                "text": text,
                "at": _now_iso(),
            })
    elif "doneStep" in op:
        sid = op["doneStep"]
        for key in list(data["steps"].keys()):
            data["steps"][key] = [x for x in data["steps"][key] if x.get("id") != sid]
    elif "setPlan" in op:
        p = op["setPlan"] or {}
        did = (str(p.get("deadlineId") or "")).strip()
        plan = p.get("plan")
        if did and isinstance(plan, dict) and isinstance(plan.get("sessions"), list):
            data.setdefault("plans", {})[did] = plan
    elif "addTask" in op:
        t = op["addTask"] or {}
        tid = (str(t.get("id") or "")).strip() or "t_" + uuid.uuid4().hex[:10]
        title = (t.get("title") or "").strip()
        if title:
            data.setdefault("tasks", {})[tid] = {"title": title[:200], "at": _now_iso()}
    elif "removeTask" in op:
        tid = str(op["removeTask"] or "")
        data.setdefault("tasks", {}).pop(tid, None)
        data.setdefault("plans", {}).pop(tid, None)
    elif "clearPlan" in op:
        data.setdefault("plans", {}).pop(str(op["clearPlan"] or ""), None)
    elif "addAbsence" in op:
        # a class she missed or came late to; the policy that decides what it
        # costs lives with the course in ~/.courses.json, not here
        a = op["addAbsence"] or {}
        key = (str(a.get("courseKey") or "")).strip()
        day = (str(a.get("date") or "")).strip()[:10]
        kind = a.get("kind") if a.get("kind") in ("absent", "late") else "absent"
        if key and _is_day(day):
            aid = (str(a.get("id") or "")).strip() or "ab_" + uuid.uuid4().hex[:10]
            data.setdefault("absences", {})[aid] = {
                "courseKey": key, "date": day, "kind": kind,
                "excused": bool(a.get("excused")),
                "note": (str(a.get("note") or "")).strip()[:200], "at": _now_iso(),
            }
    elif "removeAbsence" in op:
        data.setdefault("absences", {}).pop(str(op["removeAbsence"] or ""), None)
    elif "setAbsence" in op:
        a = op["setAbsence"] or {}
        row = data.setdefault("absences", {}).get(str(a.get("id") or ""))
        if row is not None:
            if "excused" in a:
                row["excused"] = bool(a["excused"])
            if a.get("kind") in ("absent", "late"):
                row["kind"] = a["kind"]
            if "note" in a:
                row["note"] = (str(a.get("note") or "")).strip()[:200]
    return data


def _is_day(text):
    try:
        datetime.strptime(text, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def logged_hours(data):
    """(hours by deadlineId, hours by courseKey). Untagged sessions count in neither."""
    mins_dl, mins_course = {}, {}
    for s in data.get("sessions", []):
        try:
            m = int(s.get("minutes") or 0)
        except (TypeError, ValueError):
            m = 0
        if s.get("deadlineId"):
            mins_dl[s["deadlineId"]] = mins_dl.get(s["deadlineId"], 0) + m
        if s.get("courseKey"):
            mins_course[s["courseKey"]] = mins_course.get(s["courseKey"], 0) + m
    to_h = lambda d: {k: round(v / 60.0, 4) for k, v in d.items()}
    return to_h(mins_dl), to_h(mins_course)
