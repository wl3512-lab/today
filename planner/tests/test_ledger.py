import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ledger


class LedgerFileTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        self.path = os.path.join(self.dir, "ledger.json")

    def test_missing_file_is_empty_ledger(self):
        self.assertEqual(ledger.load(self.path), {"sessions": [], "steps": {}, "notes": {}, "plans": {}, "calEvents": {}, "tasks": {}, "absences": {}})

    def test_save_then_load_roundtrips(self):
        data = {"sessions": [{"at": "2026-09-15T18:00:00Z", "minutes": 25,
                              "courseKey": "coding", "deadlineId": "abc"}],
                "steps": {"coding": [{"id": "s1", "text": "email TA", "at": "2026-09-15T18:00:00Z"}]},
                "notes": {}, "plans": {}, "calEvents": {}, "tasks": {}, "absences": {}}
        ledger.save(self.path, data)
        self.assertEqual(ledger.load(self.path), data)

    def test_save_is_atomic_leaves_no_tmp(self):
        ledger.save(self.path, {"sessions": [], "steps": {}})
        self.assertEqual(sorted(os.listdir(self.dir)), ["ledger.json"])

    def test_corrupt_file_is_set_aside_not_overwritten(self):
        with open(self.path, "w") as f:
            f.write("{not json")
        self.assertEqual(ledger.load(self.path), {"sessions": [], "steps": {}, "notes": {}, "plans": {}, "calEvents": {}, "tasks": {}, "absences": {}})
        names = os.listdir(self.dir)
        self.assertEqual(len(names), 1)
        self.assertTrue(names[0].startswith("ledger.json.corrupt-"))
        with open(os.path.join(self.dir, names[0])) as f:
            self.assertEqual(f.read(), "{not json")

    def test_load_defaults_notes(self):
        ledger.save(self.path, {"sessions": [], "steps": {}})
        self.assertEqual(ledger.load(self.path)["notes"], {})

    def test_load_defaults_plans(self):
        ledger.save(self.path, {"sessions": [], "steps": {}})
        self.assertEqual(ledger.load(self.path)["plans"], {})

    def test_non_dict_json_is_empty_ledger(self):
        with open(self.path, "w") as f:
            json.dump([1, 2], f)
        self.assertEqual(ledger.load(self.path)["sessions"], [])

    def test_unreadable_file_is_not_renamed(self):
        with open(self.path, "w") as f:
            f.write('{"sessions": [], "steps": {}}')
        with patch("ledger.open", side_effect=OSError("permission denied")):
            self.assertEqual(ledger.load(self.path), {"sessions": [], "steps": {}, "notes": {}, "plans": {}, "calEvents": {}, "tasks": {}, "absences": {}})
        self.assertEqual(os.listdir(self.dir), ["ledger.json"])
        with open(self.path) as f:
            self.assertEqual(f.read(), '{"sessions": [], "steps": {}}')

    def test_corrupt_file_rename_failure_does_not_raise(self):
        with open(self.path, "w") as f:
            f.write("{not json")
        with patch("ledger.os.replace", side_effect=OSError("nope")):
            self.assertEqual(ledger.load(self.path), {"sessions": [], "steps": {}, "notes": {}, "plans": {}, "calEvents": {}, "tasks": {}, "absences": {}})
        self.assertEqual(os.listdir(self.dir), ["ledger.json"])
        with open(self.path) as f:
            self.assertEqual(f.read(), "{not json")


class LedgerOpsTests(unittest.TestCase):
    def empty(self):
        return {"sessions": [], "steps": {}, "notes": {}, "plans": {}, "calEvents": {}, "tasks": {}}

    def test_add_task_then_remove_takes_its_plan_with_it(self):
        data = ledger.apply_op(self.empty(), {"addTask": {"id": "t_1", "title": "  laundry  "}})
        self.assertEqual(data["tasks"]["t_1"]["title"], "laundry")
        data = ledger.apply_op(data, {"setPlan": {"deadlineId": "t_1", "plan": {"sessions": [{"at": "2026-09-28T10:00"}]}}})
        data = ledger.apply_op(data, {"removeTask": "t_1"})
        self.assertEqual((data["tasks"], data["plans"]), ({}, {}))

    def test_task_needs_a_title(self):
        self.assertEqual(ledger.apply_op(self.empty(), {"addTask": {"title": " "}})["tasks"], {})

    def test_add_session_appends_with_nullable_keys(self):
        out = ledger.apply_op(self.empty(), {"addSession": {"minutes": 14}})
        s = out["sessions"][0]
        self.assertEqual(s["minutes"], 14)
        self.assertIsNone(s["courseKey"])
        self.assertIsNone(s["deadlineId"])
        self.assertTrue(s["at"].endswith("Z"))

    def test_add_session_rejects_zero_minutes(self):
        out = ledger.apply_op(self.empty(), {"addSession": {"minutes": 0}})
        self.assertEqual(out["sessions"], [])

    def test_add_session_rejects_infinite_minutes(self):
        out = ledger.apply_op(self.empty(), {"addSession": {"minutes": float("inf")}})
        self.assertEqual(out["sessions"], [])

    def test_add_step_gets_id_and_lands_under_course(self):
        out = ledger.apply_op(self.empty(), {"addStep": {"courseKey": "coding", "text": "email TA"}})
        step = out["steps"]["coding"][0]
        self.assertEqual(step["text"], "email TA")
        self.assertTrue(step["id"].startswith("s_"))

    def test_add_step_ignores_blank_text(self):
        out = ledger.apply_op(self.empty(), {"addStep": {"courseKey": "coding", "text": "  "}})
        self.assertEqual(out["steps"], {})

    def test_done_step_removes_by_id_anywhere(self):
        data = ledger.apply_op(self.empty(), {"addStep": {"courseKey": "coding", "text": "a"}})
        data = ledger.apply_op(data, {"addStep": {"courseKey": "media", "text": "b"}})
        sid = data["steps"]["media"][0]["id"]
        data = ledger.apply_op(data, {"doneStep": sid})
        self.assertEqual(data["steps"]["media"], [])
        self.assertEqual(len(data["steps"]["coding"]), 1)

    def test_unknown_op_is_noop(self):
        self.assertEqual(ledger.apply_op(self.empty(), {"bogus": 1}), self.empty())

    def test_add_session_keeps_sid(self):
        out = ledger.apply_op(self.empty(), {"addSession": {"minutes": 25, "sid": "c_abc"}})
        self.assertEqual(out["sessions"][0]["sid"], "c_abc")

    def test_remove_session_by_sid(self):
        data = ledger.apply_op(self.empty(), {"addSession": {"minutes": 25, "sid": "c_1"}})
        data = ledger.apply_op(data, {"addSession": {"minutes": 10, "sid": "c_2"}})
        data = ledger.apply_op(data, {"removeSession": "c_1"})
        self.assertEqual([s["sid"] for s in data["sessions"]], ["c_2"])
        self.assertEqual(ledger.apply_op(data, {"removeSession": "nope"}), data)

    def test_set_note_sets_overwrites_and_clears(self):
        data = ledger.apply_op(self.empty(), {"setNote": {"deadlineId": "d1", "text": "stopped at step 3"}})
        self.assertEqual(data["notes"]["d1"]["text"], "stopped at step 3")
        self.assertTrue(data["notes"]["d1"]["at"].endswith("Z"))
        data = ledger.apply_op(data, {"setNote": {"deadlineId": "d1", "text": "  now step 4 "}})
        self.assertEqual(data["notes"]["d1"]["text"], "now step 4")
        data = ledger.apply_op(data, {"setNote": {"deadlineId": "d1", "text": "   "}})
        self.assertNotIn("d1", data["notes"])
        self.assertEqual(ledger.apply_op(data, {"setNote": {"deadlineId": "", "text": "x"}}), data)

    def test_set_plan_and_clear_plan(self):
        plan = {"madeAt": "2026-09-17T01:00:00Z", "tight": False,
                "sessions": [{"at": "2026-09-18T19:00", "minutes": 60}]}
        data = ledger.apply_op(self.empty(), {"setPlan": {"deadlineId": "d1", "plan": plan}})
        self.assertEqual(data["plans"]["d1"], plan)
        data = ledger.apply_op(data, {"setPlan": {"deadlineId": "d1", "plan": {"sessions": []}}})
        self.assertEqual(data["plans"]["d1"]["sessions"], [])
        data = ledger.apply_op(data, {"clearPlan": "d1"})
        self.assertNotIn("d1", data["plans"])
        self.assertEqual(ledger.apply_op(data, {"clearPlan": "nope"}), data)
        self.assertEqual(ledger.apply_op(data, {"setPlan": {"deadlineId": "", "plan": plan}}), data)
        self.assertEqual(ledger.apply_op(data, {"setPlan": {"deadlineId": "d2", "plan": "junk"}}), data)
        # a plan whose "sessions" isn't a list is ignored outright, not stored half-broken
        self.assertEqual(
            ledger.apply_op(data, {"setPlan": {"deadlineId": "d2", "plan": {"sessions": "nope"}}}), data)
        self.assertEqual(
            ledger.apply_op(data, {"setPlan": {"deadlineId": "d2", "plan": {"madeAt": "x"}}}), data)
        # clearPlan coerces its argument to a string, so a non-string id never raises
        data = ledger.apply_op(data, {"setPlan": {"deadlineId": "42", "plan": {"sessions": []}}})
        data = ledger.apply_op(data, {"clearPlan": 42})
        self.assertNotIn("42", data["plans"])


class RollupTests(unittest.TestCase):
    def test_logged_hours_by_deadline_and_course(self):
        data = {"sessions": [
            {"at": "x", "minutes": 30, "courseKey": "coding", "deadlineId": "d1"},
            {"at": "x", "minutes": 15, "courseKey": "coding", "deadlineId": "d1"},
            {"at": "x", "minutes": 60, "courseKey": "media", "deadlineId": "d2"},
            {"at": "x", "minutes": 10, "courseKey": None, "deadlineId": None},
        ], "steps": {}}
        by_dl, by_course = ledger.logged_hours(data)
        self.assertEqual(by_dl, {"d1": 0.75, "d2": 1.0})
        self.assertEqual(by_course, {"coding": 0.75, "media": 1.0})

    def test_logged_hours_sums_minutes_exactly_before_dividing(self):
        data = {"sessions": [
            {"at": "x", "minutes": 1, "courseKey": None, "deadlineId": "d1"}
            for _ in range(60)
        ], "steps": {}}
        by_dl, _ = ledger.logged_hours(data)
        self.assertEqual(by_dl, {"d1": 1.0})


if __name__ == "__main__":
    unittest.main()


class AbsenceOpTests(unittest.TestCase):
    def test_add_absence_records_course_day_and_kind(self):
        data = ledger.apply_op(ledger.load("/nonexistent"), {"addAbsence": {
            "id": "ab_1", "courseKey": "coding", "date": "2026-09-25", "kind": "late"}})
        row = data["absences"]["ab_1"]
        self.assertEqual((row["courseKey"], row["date"], row["kind"], row["excused"]),
                         ("coding", "2026-09-25", "late", False))

    def test_add_absence_needs_a_course_and_a_real_day(self):
        data = ledger.load("/nonexistent")
        ledger.apply_op(data, {"addAbsence": {"courseKey": "coding", "date": "someday"}})
        ledger.apply_op(data, {"addAbsence": {"date": "2026-09-25"}})
        self.assertEqual(data["absences"], {})

    def test_unknown_kind_is_an_absence(self):
        data = ledger.apply_op(ledger.load("/nonexistent"), {"addAbsence": {
            "id": "a", "courseKey": "media", "date": "2026-09-30", "kind": "nap"}})
        self.assertEqual(data["absences"]["a"]["kind"], "absent")

    def test_set_absence_marks_it_excused_and_remove_drops_it(self):
        data = ledger.apply_op(ledger.load("/nonexistent"), {"addAbsence": {
            "id": "a", "courseKey": "media", "date": "2026-09-30"}})
        ledger.apply_op(data, {"setAbsence": {"id": "a", "excused": True}})
        self.assertTrue(data["absences"]["a"]["excused"])
        ledger.apply_op(data, {"removeAbsence": "a"})
        self.assertEqual(data["absences"], {})
