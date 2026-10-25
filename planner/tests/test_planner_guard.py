"""The planner's browser holds one page: the planner."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import planner_guard as pg

PAGE = "planner.html"
PLANNER = "file:///Users/someone/today/planner/planner.html?v=1&t=x"


def page(i, url, kind="page"):
    return {"id": i, "type": kind, "url": url}


class Decide(unittest.TestCase):
    def test_lone_planner_is_left_alone(self):
        self.assertEqual(pg.decide([page("a", PLANNER)], PAGE)[:2], ([], []))

    def test_stray_links_close_and_go_to_real_chrome(self):
        close, fwd, _ = pg.decide([page("n", "https://quillbot.com/x"), page("a", PLANNER),
                                   page("w", "https://sw.js", kind="service_worker")], PAGE)
        self.assertEqual(close, ["n"])
        self.assertEqual(fwd, ["https://quillbot.com/x"])

    def test_duplicate_planners_collapse_to_the_oldest(self):
        close, fwd, _ = pg.decide([page("new", PLANNER), page("mid", PLANNER), page("old", PLANNER)], PAGE)
        self.assertEqual(close, ["new", "mid"])
        self.assertEqual(fwd, [])

    def test_blank_page_gets_a_grace_period(self):
        rows = [page("a", PLANNER), page("b", "about:blank")]
        seen = {}
        for _ in range(pg.GRACE):
            close, _, seen = pg.decide(rows, PAGE, seen)
            self.assertEqual(close, [])
        close, _, seen = pg.decide(rows, PAGE, seen)
        self.assertEqual(close, ["b"])

    def test_blank_that_became_a_link_is_forwarded(self):
        _, _, seen = pg.decide([page("a", PLANNER), page("b", "about:blank")], PAGE)
        close, fwd, seen = pg.decide([page("a", PLANNER), page("b", "https://notion.so/p")], PAGE, seen)
        self.assertEqual((close, fwd, seen), (["b"], ["https://notion.so/p"], {}))

    def test_chrome_pages_close_without_forwarding(self):
        close, fwd, _ = pg.decide([page("a", PLANNER), page("s", "chrome://settings/")], PAGE)
        self.assertEqual((close, fwd), (["s"], []))

    def test_other_local_file_is_forwarded(self):
        close, fwd, _ = pg.decide([page("a", PLANNER), page("p", "file:///Users/x/Downloads/a.pdf")], PAGE)
        self.assertEqual((close, fwd), (["p"], ["file:///Users/x/Downloads/a.pdf"]))


if __name__ == "__main__":
    unittest.main()
