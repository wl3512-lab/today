"""tools/doctor.py: the example settings pass, and common setup mistakes are named."""
import copy
import importlib.util
import json
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_spec = importlib.util.spec_from_file_location("doctor", os.path.join(ROOT, "tools", "doctor.py"))
doctor = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(doctor)


def example(name):
    with open(os.path.join(ROOT, "templates", name)) as fh:
        return json.load(fh)


class DoctorTest(unittest.TestCase):
    def setUp(self):
        self.profile = example("profile.example.json")
        self.courses = example("courses.example.json")

    def test_the_examples_are_clean(self):
        problems, notes = doctor.check_settings(self.profile, self.courses)
        self.assertEqual(problems, [])
        self.assertEqual(notes, [])

    def test_platform_without_an_address(self):
        p = copy.deepcopy(self.profile)
        p["lms"]["host"] = ""
        self.assertTrue(any("lms.host is empty" in x for x in doctor.check_settings(p, self.courses)[0]))
        p["lms"]["host"] = "https://canvas.stateu.edu"
        self.assertTrue(any("without https" in x for x in doctor.check_settings(p, self.courses)[0]))

    def test_course_mistakes(self):
        c = copy.deepcopy(self.courses)
        c["courses"].append(dict(c["courses"][0]))                    # duplicate key
        c["courses"].append({"key": "Bad Key", "name": "x"})
        c["courses"].append({"key": "late", "name": "y", "meets": {"start": "2pm"}})
        problems = doctor.check_settings(self.profile, c)[0]
        self.assertTrue(any("duplicate course keys: chem101" in x for x in problems))
        self.assertTrue(any("Bad Key: key should be lowercase" in x for x in problems))
        self.assertTrue(any("meets.start should look like 14:30" in x for x in problems))

    def test_quiz_prep_must_name_a_real_course(self):
        p = copy.deepcopy(self.profile)
        p["quizPrep"]["courses"] = ["chem102"]
        self.assertTrue(any("chem102" in x for x in doctor.check_settings(p, self.courses)[0]))

    def test_notes_for_missing_ids_and_odd_weights(self):
        c = copy.deepcopy(self.courses)
        c["courses"][0]["lmsId"] = None
        c["courses"][0]["gradeScheme"]["weights"]["Final"] = 0.5
        notes = doctor.check_settings(self.profile, c)[1]
        self.assertTrue(any("no lmsId" in x for x in notes))
        self.assertTrue(any("add to 1.15" in x for x in notes))

    def test_no_sync_yet_is_a_note(self):
        self.assertEqual(doctor.check_sync("/nonexistent/cache.json"),
                         ([], ["no course sync yet (it runs during install, then every 2 hours)"]))


if __name__ == "__main__":
    unittest.main()
