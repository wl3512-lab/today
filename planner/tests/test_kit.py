import os
import subprocess
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import kit

CODING = {
    "key": "coding", "short": "Coding",
    "links": [
        {"kind": "github-weekly", "url": "https://github.com/cs110-class/content-2026", "role": "weekly notes", "access": "public"},
        {"kind": "github-wiki", "url": "https://github.com/cs110-class/content-2026/wiki", "role": "homework wiki", "access": "public"},
        {"kind": "gdoc", "url": "https://docs.google.com/x", "role": "syllabus", "access": "LOCKED - needs login"},
        {"kind": "brightspace", "url": None, "role": "links only", "access": "session"},
    ],
    "kit": {"apps": ["Xcode"]},
}


class BuildRowsTests(unittest.TestCase):
    def ids(self, rows):
        return [r["id"] for r in rows]

    def test_row_order(self):
        rows = kit.build_rows(CODING, playlist="https://soundcloud.com/me/sets/study")
        self.assertEqual(self.ids(rows), ["playlist", "tabs", "notes", "app:Xcode", "focus", "physical"])

    def test_tabs_skip_locked_and_urlless_links(self):
        rows = kit.build_rows(CODING, playlist=None)
        tabs = [r for r in rows if r["id"] == "tabs"][0]
        self.assertEqual(tabs["urls"], ["https://github.com/cs110-class/content-2026",
                                        "https://github.com/cs110-class/content-2026/wiki"])
        self.assertEqual(tabs["label"], "2 tabs")
        self.assertEqual(tabs["detail"], "weekly notes · homework wiki")

    def test_tabs_label_is_singular_for_one_tab(self):
        course = {"key": "x", "links": [
            {"kind": "gdoc", "url": "https://docs.google.com/x", "role": "syllabus", "access": "public"},
        ]}
        tabs = [r for r in kit.build_rows(course, playlist=None) if r["id"] == "tabs"][0]
        self.assertEqual(tabs["label"], "1 tab")

    def test_tabs_detail_shortens_long_sentence_roles(self):
        course = {"key": "x", "links": [
            {"kind": "github-weekly", "url": "https://example.com/a",
             "role": "weekly notes; each week's '## Homework WeekNN' is that week's assignment",
             "access": "public"},
        ]}
        tabs = [r for r in kit.build_rows(course, playlist=None) if r["id"] == "tabs"][0]
        self.assertEqual(tabs["detail"], "weekly notes")

    def test_only_the_first_brightspace_url_opens_with_the_kit(self):
        bs = "https://brightspace.example.edu/d2l/"
        hw = {"title": "HW 2", "url": bs + "lms/dropbox/user/folder_submit_files.d2l?db=1&ou=9"}
        mats = [{"title": "Lesson 4", "url": bs + "le/content/9/viewContent/1/View"},
                {"title": "slides", "url": "https://docs.google.com/presentation/d/x"}]
        course = dict(CODING, brightspaceId="9")
        rows = {r["id"]: r for r in kit.build_rows(course, playlist=None, assignment=hw, materials=mats)}
        self.assertEqual(rows["homework"]["cmd"], kit._open([hw["url"]]))
        self.assertNotIn("held", rows["homework"])
        # the material on Brightspace waits; the Google slide still opens now
        self.assertEqual(rows["materials"]["held"], [mats[0]["url"]])
        self.assertEqual(rows["materials"]["cmd"], kit._open([mats[1]["url"]]))
        self.assertIn("1 on Brightspace opens when your desk is ready", rows["materials"]["detail"])
        # the course Content tab is Brightspace too: held, and the row runs nothing
        self.assertEqual(rows["tabs"]["held"], [bs + "le/content/9/Home"])
        self.assertEqual(rows["tabs"]["cmd"], kit._open([u for u in rows["tabs"]["urls"] if not kit.is_brightspace(u)]))
        # a row whose every url is on Brightspace runs nothing now
        only = {r["id"]: r for r in kit.build_rows({"key": "x", "brightspaceId": "9",
                                                    "links": [{"kind": "brightspace", "url": None}]},
                                                   playlist=None, assignment=hw)}
        self.assertIsNone(only["tabs"]["cmd"])
        self.assertEqual(only["tabs"]["held"], [bs + "le/content/9/Home"])

    def test_without_homework_the_first_brightspace_material_is_the_door(self):
        bs = "https://brightspace.example.edu/d2l/le/content/9/"
        mats = [{"title": "a", "url": bs + "a"}, {"title": "b", "url": bs + "b"}]
        rows = {r["id"]: r for r in kit.build_rows(CODING, playlist=None, materials=mats)}
        self.assertEqual(rows["materials"]["cmd"], kit._open([bs + "a"]))
        self.assertEqual(rows["materials"]["held"], [bs + "b"])

    def test_no_playlist_means_no_playlist_row(self):
        rows = kit.build_rows(CODING, playlist=None)
        self.assertNotIn("playlist", self.ids(rows))

    def test_web_playlist_opens_as_a_tab_and_says_press_play(self):
        url = "https://soundcloud.com/me/sets/study"
        pl = [r for r in kit.build_rows(CODING, playlist=url) if r["id"] == "playlist"][0]
        self.assertEqual(pl["label"], "playlist open - press play")
        self.assertEqual(pl["cmd"], kit._open([url]))

    def test_only_a_web_playlist_makes_a_row(self):
        # Spotify is gone from the kit: a leftover URI in the registry is not a playlist
        self.assertNotIn("playlist", self.ids(kit.build_rows(CODING, playlist="spotify:playlist:abc")))

    def test_music_off_marks_playlist_skipped(self):
        rows = kit.build_rows(CODING, playlist="https://soundcloud.com/me/sets/study", music_off=True)
        pl = [r for r in rows if r["id"] == "playlist"][0]
        self.assertTrue(pl["skip"])

    def test_notes_defaults_to_fall_page_and_overrides(self):
        rows = kit.build_rows(CODING, playlist=None)
        self.assertEqual([r for r in rows if r["id"] == "notes"][0]["cmd"][-1], kit.DEFAULT_NOTES)
        custom = dict(CODING, kit={"notes": "https://notion.so/coding"})
        rows = kit.build_rows(custom, playlist=None)
        self.assertEqual([r for r in rows if r["id"] == "notes"][0]["cmd"][-1], "https://notion.so/coding")

    def test_physical_defaults_and_overrides(self):
        rows = kit.build_rows(CODING, playlist=None)
        self.assertEqual(rows[-1]["items"], kit.DEFAULT_PHYSICAL)
        custom = dict(CODING, kit={"physical": ["headphones"]})
        self.assertEqual(kit.build_rows(custom, playlist=None)[-1]["items"], ["headphones"])

    def test_course_without_kit_or_links_still_has_notes_focus_physical(self):
        rows = kit.build_rows({"key": "x", "links": []}, playlist=None)
        self.assertEqual(self.ids(rows), ["notes", "focus", "physical"])

    def test_tabs_uses_chrome_when_installed(self):
        with mock.patch("kit.os.path.isdir", return_value=True):
            rows = kit.build_rows(CODING, playlist=None)
        tabs = [r for r in rows if r["id"] == "tabs"][0]
        self.assertEqual(tabs["cmd"][:4], ["open", "-na", "Google Chrome", "--args"])

    def test_urls_with_spaces_are_not_paths(self):
        hw = {"title": "Syllabus", "url": "https://brightspace.example.edu/content/enforced/1-x/WRIT150 Syllabus.docx"}
        with mock.patch("kit.os.path.isdir", return_value=True):
            rows = kit.build_rows(CODING, playlist=None, assignment=hw)
        home = [r for r in rows if r["id"] == "homework"][0]
        self.assertEqual(home["cmd"][-1], "https://brightspace.example.edu/content/enforced/1-x/WRIT150%20Syllabus.docx")

    def test_tabs_falls_back_to_open_when_chrome_missing(self):
        with mock.patch("kit.os.path.isdir", return_value=False):
            rows = kit.build_rows(CODING, playlist=None)
        tabs = [r for r in rows if r["id"] == "tabs"][0]
        self.assertEqual(tabs["cmd"][0], "open")
        self.assertEqual(tabs["cmd"][1], "https://github.com/cs110-class/content-2026")
        self.assertNotIn("-a", tabs["cmd"])


class HomeworkRowTests(unittest.TestCase):
    def test_homework_row_comes_first_and_is_deduped_from_tabs(self):
        hw = {"title": "Week 03 homework: Swift UI 1", "url": "https://github.com/cs110-class/content-2026/blob/HEAD/weeks/03_swiftui.md#homework-week03"}
        rows = kit.build_rows(CODING, playlist=None, assignment=hw)
        ids = [r["id"] for r in rows]
        self.assertEqual(ids[:2], ["homework", "tabs"])
        self.assertEqual(rows[0]["label"], "this homework")
        self.assertEqual(rows[0]["detail"], "Week 03 homework: Swift UI 1")
        self.assertEqual(rows[0]["cmd"][-1], hw["url"])
        self.assertNotIn(hw["url"], rows[1]["urls"])

    def test_homework_row_replaces_a_matching_class_link(self):
        hw = {"title": "x", "url": "https://github.com/cs110-class/content-2026/wiki"}
        rows = kit.build_rows(CODING, playlist=None, assignment=hw)
        tabs = [r for r in rows if r["id"] == "tabs"][0]
        self.assertEqual(tabs["urls"], ["https://github.com/cs110-class/content-2026"])

    def test_no_homework_row_without_url(self):
        rows = kit.build_rows(CODING, playlist=None, assignment={"title": "no link"})
        self.assertNotIn("homework", [r["id"] for r in rows])

    def test_course_with_no_links_still_opens_the_homework(self):
        rows = kit.build_rows({"key": "writing", "links": []}, playlist=None,
                              assignment={"title": "Post here after class", "url": "https://brightspace.example.edu/d2l/le/1/discussions/topics/2/View"})
        self.assertEqual([r["id"] for r in rows], ["homework", "notes", "focus", "physical"])


class MaterialsRowTests(unittest.TestCase):
    def test_materials_open_after_the_homework_and_before_class_links(self):
        mats = [{"title": "STAT101 Lesson 2 - Conditional Probability", "url": "https://bs/l2"},
                {"title": "Lesson 2 Part I Annotated", "url": "https://bs/n2"}]
        rows = kit.build_rows(CODING, playlist=None, assignment={"title": "Quiz 2", "url": "https://hw"}, materials=mats)
        ids = [r["id"] for r in rows]
        self.assertEqual(ids[:3], ["homework", "materials", "tabs"])
        m = rows[1]
        self.assertEqual(m["label"], "2 materials")
        self.assertEqual(m["urls"], ["https://bs/l2", "https://bs/n2"])
        self.assertEqual(m["detail"], "STAT101 Lesson 2 - Conditional Probability · Lesson 2 Part I Annotated")
        self.assertNotIn("https://bs/l2", rows[2]["urls"])

    def test_materials_dedupe_against_class_links_and_cap_at_four(self):
        mats = [{"title": "wiki", "url": "https://github.com/cs110-class/content-2026/wiki"}] + \
               [{"title": "m%d" % i, "url": "https://m/%d" % i} for i in range(6)]
        rows = kit.build_rows(CODING, playlist=None, materials=mats)
        m = [r for r in rows if r["id"] == "materials"][0]
        self.assertEqual(len(m["urls"]), 4)
        tabs = [r for r in rows if r["id"] == "tabs"][0]
        self.assertNotIn("https://github.com/cs110-class/content-2026/wiki", tabs["urls"])

    def test_no_materials_row_when_empty_or_junk(self):
        self.assertNotIn("materials", [r["id"] for r in kit.build_rows(CODING, playlist=None, materials=[])])
        self.assertNotIn("materials", [r["id"] for r in kit.build_rows(CODING, playlist=None, materials="junk")])


class BrightspaceTabTests(unittest.TestCase):
    def test_brightspace_only_course_opens_its_content_page(self):
        course = {"key": "writing", "brightspaceId": 123456,
                  "links": [{"kind": "brightspace", "url": None, "role": "syllabus + assignments", "access": "session"}]}
        rows = kit.build_rows(course, playlist=None, assignment={"title": "Week #4", "url": "https://hw"})
        tabs = [r for r in rows if r["id"] == "tabs"][0]
        self.assertEqual(tabs["urls"], ["https://brightspace.example.edu/d2l/le/content/123456/Home"])


class BrowsableLinkTests(unittest.TestCase):
    def test_csv_export_links_open_as_the_readable_sheet(self):
        course = {"key": "stat101", "links": [
            {"kind": "gsheet-csv", "url": "https://docs.google.com/spreadsheets/d/e/X/pub?output=csv", "role": "schedule", "access": "public"},
            {"kind": "gdoc", "url": "https://docs.google.com/document/d/e/Y/pub", "role": "syllabus", "access": "public"}]}
        rows = kit.build_rows(course, playlist=None)
        tabs = [r for r in rows if r["id"] == "tabs"][0]
        self.assertEqual(tabs["urls"], ["https://docs.google.com/spreadsheets/d/e/X/pubhtml", "https://docs.google.com/document/d/e/Y/pub"])

    def test_readable_sheet_homework_dedupes_the_csv_link(self):
        course = {"key": "stat101", "links": [
            {"kind": "gsheet-csv", "url": "https://docs.google.com/spreadsheets/d/e/X/pub?output=csv", "role": "schedule", "access": "public"}]}
        rows = kit.build_rows(course, playlist=None, assignment={"title": "Homework 2", "url": "https://docs.google.com/spreadsheets/d/e/X/pubhtml"})
        self.assertEqual([r["id"] for r in rows], ["homework", "notes", "focus", "physical"])


class RunRowsTests(unittest.TestCase):
    def test_runner_is_called_per_command_row_and_results_recorded(self):
        calls = []

        def fake_run(cmd, **kw):
            calls.append(cmd)
            class R: returncode = 0; stderr = ""
            return R()

        rows = kit.build_rows(CODING, playlist="https://soundcloud.com/me/sets/study")
        out = kit.run_rows(rows, runner=fake_run)
        self.assertEqual(len(calls), 5)          # playlist, tabs, notes, app, focus
        self.assertTrue(all(r["ok"] for r in out if r["cmd"]))
        self.assertIsNone(out[-1]["ok"])         # physical is never run
        self.assertEqual(out[-1]["items"], kit.DEFAULT_PHYSICAL)
        tabs = [r for r in out if r["id"] == "tabs"][0]
        self.assertEqual(tabs["detail"], "weekly notes · homework wiki")

    def test_failed_command_reports_first_stderr_line_and_continues(self):
        def fake_run(cmd, **kw):
            class R:
                returncode = 1 if cmd[0] == "shortcuts" else 0
                stderr = "no shortcut named Study\nmore"
            return R()

        out = kit.run_rows(kit.build_rows(CODING, playlist=None), runner=fake_run)
        focus = [r for r in out if r["id"] == "focus"][0]
        self.assertFalse(focus["ok"])
        self.assertEqual(focus["detail"], "make a Shortcut called Study")
        self.assertTrue([r for r in out if r["id"] == "notes"][0]["ok"])

    def test_skipped_row_is_not_run(self):
        calls = []

        def fake_run(cmd, **kw):
            calls.append(cmd[0])
            class R: returncode = 0; stderr = ""
            return R()

        rows = kit.build_rows(CODING, playlist="https://soundcloud.com/me/sets/study", music_off=True)
        out = kit.run_rows(rows, runner=fake_run)
        self.assertNotIn("osascript", calls)
        self.assertIsNone(out[0]["ok"])
        self.assertEqual(out[0]["detail"], "off for today")

    def test_exception_from_runner_is_a_failed_row(self):
        def boom(cmd, **kw):
            raise OSError("no such binary")
        out = kit.run_rows(kit.build_rows({"key": "x", "links": []}, playlist=None), runner=boom)
        self.assertFalse(out[0]["ok"])
        self.assertIn("no such binary", out[0]["detail"])

    def test_music_and_stop_commands(self):
        self.assertEqual(kit.music_cmd("play", "https://soundcloud.com/me/sets/study"),
                         kit._open(["https://soundcloud.com/me/sets/study"]))
        self.assertIsNone(kit.music_cmd("play", None))
        self.assertIsNone(kit.music_cmd("play", "spotify:playlist:abc"))
        self.assertIsNone(kit.music_cmd("pause", None))
        self.assertEqual(kit.stop_cmds(), [["shortcuts", "run", "Study Off"]])

    def test_run_music_pause_is_a_no_op_that_reports_ok(self):
        calls = []

        def fake_run(cmd, **kw):
            calls.append(cmd)

        self.assertTrue(kit.run_music("pause", "https://soundcloud.com/me/sets/study", runner=fake_run)["ok"])
        self.assertEqual(calls, [])

    def test_run_music_play_with_no_playlist_never_calls_runner_and_fails(self):
        calls = []

        def fake_run(cmd, **kw):
            calls.append(cmd)
            class R: returncode = 0; stderr = ""
            return R()

        out = kit.run_music("play", None, runner=fake_run)
        self.assertFalse(out["ok"])
        self.assertIn("no web studyPlaylist", out["detail"])
        self.assertEqual(calls, [])

    def test_timeout_reports_readable_detail(self):
        def fake_run(cmd, **kw):
            raise subprocess.TimeoutExpired(cmd, kit.TIMEOUT)

        out = kit.run_rows(kit.build_rows({"key": "x", "links": []}, playlist=None), runner=fake_run)
        notes = [r for r in out if r["id"] == "notes"][0]
        self.assertFalse(notes["ok"])
        self.assertEqual(notes["detail"], "timed out after %ss" % kit.TIMEOUT)

    def test_missing_binary_reports_readable_detail(self):
        def fake_run(cmd, **kw):
            raise FileNotFoundError()

        out = kit.run_rows(kit.build_rows({"key": "x", "links": []}, playlist=None), runner=fake_run)
        notes = [r for r in out if r["id"] == "notes"][0]
        self.assertFalse(notes["ok"])
        self.assertEqual(notes["detail"], "missing: open")

    def test_stderr_multiline_reports_first_line(self):
        def fake_run(cmd, **kw):
            class R: returncode = 1; stderr = "line1\nline2"
            return R()

        out = kit.run_rows(kit.build_rows({"key": "x", "links": []}, playlist=None), runner=fake_run)
        notes = [r for r in out if r["id"] == "notes"][0]
        self.assertFalse(notes["ok"])
        self.assertEqual(notes["detail"], "line1")

    def test_stderr_empty_reports_exit_code(self):
        def fake_run(cmd, **kw):
            class R: returncode = 1; stderr = ""
            return R()

        out = kit.run_rows(kit.build_rows({"key": "x", "links": []}, playlist=None), runner=fake_run)
        notes = [r for r in out if r["id"] == "notes"][0]
        self.assertFalse(notes["ok"])
        self.assertEqual(notes["detail"], "exit 1")


if __name__ == "__main__":
    unittest.main()
