"""A running average: platform scores weighted by the syllabus."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import grades

SCHEME = {"weights": {"Homework": 0.05, "Quizzes": 0.20, "Exam 1": 0.20, "Exam 2": 0.20, "Final Exam": 0.35},
          "drops": {"Homework": 2, "Quizzes": 3}}


def item(name, points, out_of, at="2026-09-28T17:33:34Z"):
    return {"title": "%s: %s / %s" % (name, points, out_of), "at": at,
            "meta": {"gradeItem": name, "points": points, "outOf": out_of}}


# a made-up gradebook in the shape Brightspace sends: category rows it already averaged, plus the items
REAL = [item("Homework", 94, 100), item("Quizzes", 82.2, 100),
        item("Quiz 1", 7, 10), item("Quiz 2", 9, 10),
        item("Homework 1", 40, 45), item("Homework 2", 30, 30)]


class Summarize(unittest.TestCase):
    def test_gradebook(self):
        s = grades.summarize(REAL, SCHEME)
        # (0.05 * 94 + 0.20 * 82.2) / 0.25
        self.assertAlmostEqual(s["average"], 84.56, places=2)
        self.assertEqual(s["letter"], "B")
        self.assertAlmostEqual(s["gradedWeight"], 0.25)
        quizzes = [c for c in s["categories"] if c["name"] == "Quizzes"][0]
        self.assertEqual([i["name"] for i in quizzes["items"]], ["Quiz 1", "Quiz 2"])
        exam = [c for c in s["categories"] if c["name"] == "Exam 1"][0]
        self.assertIsNone(exam["pct"])

    def test_carries_drop_rules_and_scale(self):
        scheme = dict(SCHEME, outOf={"Homework": 12, "Quizzes": 12})
        s = grades.summarize(REAL, scheme)
        cats = {c["name"]: c for c in s["categories"]}
        self.assertEqual((cats["Homework"]["drops"], cats["Homework"]["outOf"]), (2, 12))
        self.assertEqual((cats["Quizzes"]["drops"], cats["Quizzes"]["outOf"]), (3, 12))
        self.assertEqual((cats["Exam 1"]["drops"], cats["Exam 1"]["outOf"]), (0, None))
        self.assertEqual(s["scale"][0], ["A", 93])

    def test_exam_counts_once_posted(self):
        s = grades.summarize(REAL + [item("Exam 1", 45, 50)], SCHEME)
        # (4.7 + 16.44 + 0.20 * 90) / 0.45
        self.assertAlmostEqual(s["average"], (4.7 + 16.44 + 18) / 0.45, places=2)

    def test_category_row_missing_uses_items_with_drops(self):
        rows = [item("Quiz %d" % n, p, 10) for n, p in enumerate([4, 9, 10, 8, 6], 1)]
        s = grades.summarize(rows, {"weights": {"Quizzes": 1.0}, "drops": {"Quizzes": 3}})
        self.assertAlmostEqual(s["average"], 95.0)          # 4, 6, 8 dropped

    def test_needs_on_whats_left(self):
        # an exam scored 0 is cut to 10% mid-term, and the final raised to 45%
        scheme = {"weights": {"Homework": 0.05, "Quizzes": 0.20, "Exam 1": 0.10, "Exam 2": 0.20, "Final Exam": 0.45},
                  "changes": [{"date": "2026-03-02", "text": "Exam 1 20% to 10%, final 35% to 45%"}]}
        s = grades.summarize([item("Homework", 95, 100), item("Quizzes", 80, 100), item("Exam 1", 0, 100)], scheme)
        self.assertEqual(s["left"], ["Exam 2", "Final Exam"])
        need = {n["letter"]: n["need"] for n in s["needs"]}
        # banked 0.05 * 95 + 0.20 * 80 = 20.75 of 100, with 65% still to come
        self.assertAlmostEqual(need["C"], round((65 - 20.75) / 0.65, 1))
        self.assertAlmostEqual(need["C+"], round((75 - 20.75) / 0.65, 1))
        self.assertGreater(need["A"], 100)                  # out of reach
        self.assertNotIn("F", need)
        self.assertEqual(s["changes"][0]["date"], "2026-03-02")

    def test_no_needs_once_everything_is_graded(self):
        s = grades.summarize([item("Quizzes", 80, 100)], {"weights": {"Quizzes": 1.0}})
        self.assertEqual((s["needs"], s["left"], s["changes"]), ([], [], []))

    def test_no_scheme_or_nothing_graded(self):
        self.assertIsNone(grades.summarize(REAL, None))
        self.assertIsNone(grades.summarize([], SCHEME))
        self.assertIsNone(grades.summarize([item("Homework", 5, 0)], SCHEME))

    def test_letter_boundaries(self):
        self.assertEqual(grades.letter(93), "A")
        self.assertEqual(grades.letter(92.99), "A-")
        self.assertEqual(grades.letter(83), "B")
        self.assertEqual(grades.letter(49.9), "F")


if __name__ == "__main__":
    unittest.main()
