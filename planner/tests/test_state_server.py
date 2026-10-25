import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import kit
import ledger
import state_server
from state_server import (
    DEFAULT_STATE,
    format_title,
    load_state,
    save_state,
    should_notify,
    start_server,
)


class LoadSaveStateTests(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp()
        os.close(fd)
        os.remove(self.path)

    def tearDown(self):
        if os.path.exists(self.path):
            os.remove(self.path)

    def test_load_missing_file_returns_default(self):
        self.assertEqual(load_state(self.path), DEFAULT_STATE)

    def test_save_then_load_roundtrips(self):
        save_state(self.path, {"oneThing": "finish invoice", "stackAfter": "coffee", "done": False})
        # anchors ride along with the day state (see DEFAULT_STATE), so a
        # save that omits them reads back with the defaults filled in.
        self.assertEqual(
            load_state(self.path),
            {"oneThing": "finish invoice", "stackAfter": "coffee", "done": False,
             "anchors": [], "anchorsDate": "", "focus": ""},
        )

    def test_load_malformed_json_returns_default(self):
        with open(self.path, "w") as f:
            f.write("{not valid json")
        self.assertEqual(load_state(self.path), DEFAULT_STATE)

    def test_save_ignores_unknown_keys(self):
        saved = save_state(self.path, {"oneThing": "x", "evil": "ignored"})
        self.assertNotIn("evil", saved)


class FormatTitleTests(unittest.TestCase):
    def test_empty_one_thing(self):
        self.assertEqual(format_title("", False), "\U0001FAA9")

    def test_done(self):
        self.assertEqual(format_title("finish invoice", True), "\U0001FAA9 ✓")

    def test_short_one_thing(self):
        self.assertEqual(format_title("call mom", False), "\U0001FAA9 call mom")

    def test_long_one_thing_truncates(self):
        long_text = "a" * 30
        result = format_title(long_text, False)
        self.assertEqual(result, "\U0001FAA9 " + "a" * 20 + "…")


class ShouldNotifyTests(unittest.TestCase):
    def test_empty_one_thing_no_notify(self):
        self.assertFalse(should_notify("", False))

    def test_done_no_notify(self):
        self.assertFalse(should_notify("finish invoice", True))

    def test_pending_one_thing_notifies(self):
        self.assertTrue(should_notify("finish invoice", False))


class StateServerHTTPTests(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp()
        os.close(fd)
        os.remove(self.path)
        self.server, self.thread = start_server(self.path, port=0)
        self.port = self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(timeout=2)
        if os.path.exists(self.path):
            os.remove(self.path)

    def _url(self, path):
        return "http://127.0.0.1:%d%s" % (self.port, path)

    def test_get_state_default(self):
        with urllib.request.urlopen(self._url("/state"), timeout=5) as resp:
            data = json.loads(resp.read())
        self.assertEqual(data, DEFAULT_STATE)

    def test_ai_routes_refuse_without_the_token(self):
        # the port answers any website; running Claude needs the planner's key
        import ai_help
        for path in ("/ai/open", "/ai/chat", "/ai/terminal"):   # plugin routes: see personal/tests
            req = urllib.request.Request(
                self._url(path), data=json.dumps({"courseKey": "applab", "token": "guess"}).encode(),
                method="POST", headers={"Content-Type": "application/json"})
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(req, timeout=5)
            self.assertEqual(ctx.exception.code, 403)

    def test_post_then_get_roundtrips(self):
        payload = json.dumps({"oneThing": "walk dog", "stackAfter": "", "done": False}).encode("utf-8")
        req = urllib.request.Request(
            self._url("/state"), data=payload, method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            posted = json.loads(resp.read())
        self.assertEqual(posted["oneThing"], "walk dog")
        with urllib.request.urlopen(self._url("/state"), timeout=5) as resp:
            fetched = json.loads(resp.read())
        self.assertEqual(fetched["oneThing"], "walk dog")


class PlannerPingTests(unittest.TestCase):
    """The planner's heartbeat - what the menubar checks before opening a window."""

    def setUp(self):
        fd, self.path = tempfile.mkstemp()
        os.close(fd)
        os.remove(self.path)
        state_server.note_planner(False)
        self.server, self.thread = start_server(self.path, port=0)
        self.port = self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(timeout=2)
        state_server.note_planner(False)
        if os.path.exists(self.path):
            os.remove(self.path)

    def _url(self, path):
        return "http://127.0.0.1:%d%s" % (self.port, path)

    def _post(self, path, body=b""):
        req = urllib.request.Request(self._url(path), data=body, method="POST")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())

    def test_closed_until_the_planner_pings(self):
        self.assertFalse(state_server.planner_is_open(self.port))
        self.assertTrue(self._post("/ping")["open"])
        self.assertTrue(state_server.planner_is_open(self.port))

    def test_bye_beacon_closes_it_again(self):
        self._post("/ping")
        # sendBeacon sends a text body, which the route must tolerate.
        self.assertFalse(self._post("/ping?bye", b"bye")["open"])
        self.assertFalse(state_server.planner_is_open(self.port))

    def test_stale_heartbeat_counts_as_closed(self):
        self._post("/ping")
        state_server._planner["seen"] -= state_server.PLANNER_OPEN_WINDOW + 1
        self.assertFalse(state_server.planner_is_open(self.port))

    def test_no_server_means_closed(self):
        self.server.shutdown()
        self.server.server_close()
        self.assertFalse(state_server.planner_is_open(self.port, timeout=0.2))


class StorageBackupTests(unittest.TestCase):
    """The planner's localStorage, mirrored so a fresh browser profile can restore it."""

    def setUp(self):
        fd, self.path = tempfile.mkstemp()
        os.close(fd)
        os.remove(self.path)
        self._backup = state_server.STORAGE_BACKUP
        state_server.STORAGE_BACKUP = self.path + ".storage"
        self.server, self.thread = start_server(self.path, port=0)
        self.port = self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(timeout=2)
        for p in (self.path, state_server.STORAGE_BACKUP):
            if os.path.exists(p):
                os.remove(p)
        state_server.STORAGE_BACKUP = self._backup

    def _url(self, path):
        return "http://127.0.0.1:%d%s" % (self.port, path)

    def _post(self, body):
        req = urllib.request.Request(
            self._url("/storage"), data=json.dumps(body).encode("utf-8"), method="POST",
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())

    def _get(self):
        with urllib.request.urlopen(self._url("/storage"), timeout=5) as resp:
            return json.loads(resp.read())

    def test_empty_until_pushed(self):
        self.assertEqual(self._get(), {})

    def test_roundtrips_string_values(self):
        pushed = {"today-simple-v1": '{"2026-9-18":{"oneThing":"x"}}', "today.pomo": "null"}
        self.assertEqual(self._post(pushed), pushed)
        self.assertEqual(self._get(), pushed)

    def test_empty_push_never_clobbers_a_backup(self):
        self._post({"k": "v"})
        self.assertEqual(self._post({}), {"k": "v"})
        self.assertEqual(self._get(), {"k": "v"})


class OpenLinksTests(unittest.TestCase):
    """POST /kit/open hands outside links to her real browser."""

    def setUp(self):
        self.calls = []
        self._runner = state_server.KIT_RUNNER
        def runner(cmd, **kw):
            self.calls.append(cmd)
            class P: returncode = 0; stderr = ""
            return P()
        state_server.KIT_RUNNER = runner
        fd, self.path = tempfile.mkstemp(); os.close(fd); os.remove(self.path)
        self.server, self.thread = start_server(self.path, port=0)
        self.port = self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown(); self.thread.join(timeout=2)
        state_server.KIT_RUNNER = self._runner

    def _post(self, body):
        req = urllib.request.Request("http://127.0.0.1:%d/kit/open" % self.port,
                                     data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())

    def test_opens_http_urls_only(self):
        out = self._post({"urls": ["https://brightspace.example.edu/x", "javascript:alert(1)", 5]})
        self.assertTrue(out["ok"]); self.assertEqual(out["opened"], 1)
        self.assertEqual(self.calls[0][-1], "https://brightspace.example.edu/x")

    def test_no_urls_is_not_ok(self):
        self.assertFalse(self._post({"urls": []})["ok"])
        self.assertEqual(self.calls, [])


class LedgerAndKitRouteTests(unittest.TestCase):
    """Drives the real handler over HTTP with the ledger, cache and kit runner swapped."""

    def _restore_globals(self):
        state_server.LEDGER_PATH, state_server.STUDY_CACHE, state_server.KIT_RUNNER = self._orig

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        self.state = os.path.join(self.dir, "state.json")
        self.ledger = os.path.join(self.dir, "ledger.json")
        self.cache = os.path.join(self.dir, "cache.json")
        with open(self.cache, "w") as f:
            json.dump({"studyPlaylist": "https://soundcloud.com/me/sets/study", "courses": [
                {"key": "applab", "links": [{"url": "https://x", "role": "repo", "access": "public"}],
                 "kit": {"apps": ["Xcode"]}}]}, f)
        self.calls = []

        def fake_run(cmd, **kw):
            self.calls.append(cmd)
            class R: returncode = 0; stderr = ""
            return R()

        self._orig = (state_server.LEDGER_PATH, state_server.STUDY_CACHE, state_server.KIT_RUNNER)
        self.addCleanup(self._restore_globals)
        state_server.LEDGER_PATH = self.ledger
        state_server.STUDY_CACHE = self.cache
        state_server.KIT_RUNNER = fake_run
        # never reach her real Google Calendar from a test
        kick = state_server.GCAL.kick
        state_server.GCAL.kick = lambda: None
        self.addCleanup(setattr, state_server.GCAL, "kick", kick)
        self.server, _ = start_server(self.state, port=0)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.port = self.server.server_address[1]

    def req(self, path, body=None):
        url = "http://127.0.0.1:%d%s" % (self.port, path)
        data = json.dumps(body).encode() if body is not None else None
        r = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(r, timeout=5) as resp:
            return json.loads(resp.read())

    def test_get_ledger_empty(self):
        self.assertEqual(self.req("/ledger"), {"sessions": [], "steps": {}, "notes": {}, "plans": {}, "calEvents": {}, "tasks": {}, "absences": {}})

    def test_post_ledger_applies_and_persists(self):
        out = self.req("/ledger", {"addSession": {"minutes": 25, "courseKey": "applab", "deadlineId": "d1"}})
        self.assertEqual(out["sessions"][0]["minutes"], 25)
        self.assertEqual(ledger.load(self.ledger)["sessions"][0]["deadlineId"], "d1")
        out = self.req("/ledger", {"addStep": {"courseKey": "applab", "text": "email TA"}})
        self.assertEqual(out["steps"]["applab"][0]["text"], "email TA")

    def test_ledger_remove_session_and_set_note(self):
        self.req("/ledger", {"addSession": {"minutes": 25, "sid": "c_9"}})
        out = self.req("/ledger", {"removeSession": "c_9"})
        self.assertEqual(out["sessions"], [])
        out = self.req("/ledger", {"setNote": {"deadlineId": "d1", "text": "left off at the intro"}})
        self.assertEqual(out["notes"]["d1"]["text"], "left off at the intro")

    def test_ledger_set_plan_roundtrip(self):
        plan = {"madeAt": "2026-09-17T01:00:00Z", "tight": False,
                "sessions": [{"at": "2026-09-18T19:00", "minutes": 60}]}
        out = self.req("/ledger", {"setPlan": {"deadlineId": "d1", "plan": plan}})
        self.assertEqual(out["plans"]["d1"]["sessions"], plan["sessions"])

    def test_kit_run_returns_rows_and_runs_commands(self):
        out = self.req("/kit/run", {"courseKey": "applab"})
        ids = [r["id"] for r in out["rows"]]
        self.assertEqual(ids, ["playlist", "tabs", "notes", "app:Xcode", "focus", "physical"])
        self.assertEqual(len(self.calls), 5)
        self.assertEqual(out["rows"][-1]["items"], kit.DEFAULT_PHYSICAL)

    def test_kit_run_opens_the_assignment_first(self):
        out = self.req("/kit/run", {"courseKey": "applab", "assignment": {"title": "Week 03", "url": "https://hw"}})
        ids = [r["id"] for r in out["rows"]]
        self.assertEqual(ids[:3], ["playlist", "homework", "tabs"])   # the test cache has a playlist
        self.assertTrue(any("https://hw" in c for c in self.calls))

    def test_kit_run_unknown_course_still_returns_rows(self):
        out = self.req("/kit/run", {"courseKey": "nope"})
        self.assertEqual([r["id"] for r in out["rows"]], ["playlist", "notes", "focus", "physical"])

    def test_kit_run_null_course_returns_generic_rows(self):
        out = self.req("/kit/run", {"courseKey": None})
        self.assertEqual([r["id"] for r in out["rows"]], ["playlist", "notes", "focus", "physical"])

    def test_kit_music_and_stop(self):
        before = len(self.calls)
        self.assertTrue(self.req("/kit/music", {"action": "pause"})["ok"])
        self.assertEqual(len(self.calls), before)          # a SoundCloud tab: nothing to pause from here
        self.assertTrue(self.req("/kit/music", {"action": "play"})["ok"])
        self.assertIn("https://soundcloud.com/me/sets/study", self.calls[-1])
        out = self.req("/kit/stop", {})
        self.assertEqual(len(out["results"]), 1)
        self.assertEqual(self.calls[-1][:2], ["shortcuts", "run"])

    def test_pomo_route_plans_banners_and_idle_clears_them(self):
        import pomo_alerts
        made = []

        class T:
            def __init__(self, delay, fn, args=()): self.delay = delay; self.cancelled = False; made.append(self)
            def start(self): pass
            def cancel(self): self.cancelled = True

        now = 1_000_000_000_000
        old = state_server.POMO
        state_server.POMO = pomo_alerts.Scheduler(notify=lambda t, b: None, timer=T, now_ms=lambda: now)
        try:
            out = self.req("/pomo", {"phase": "work", "endAt": now + 25 * 60000, "subject": "media", "nextBreakMin": 5})
            self.assertEqual([a["title"] for a in out["scheduled"]],
                             ["Break in 2 minutes", "Break time", "Break ends in 1 minute", "Break's over"])
            self.assertEqual(self.req("/pomo", {"phase": "idle"}), {"scheduled": []})
            self.assertTrue(all(t.cancelled for t in made))
        finally:
            state_server.POMO = old

    def test_kit_music_play_without_playlist_reports_not_ok(self):
        with open(self.cache, "w") as f:
            json.dump({"courses": []}, f)
        out = self.req("/kit/music", {"action": "play"})
        self.assertFalse(out["ok"])
        self.assertEqual(self.calls, [])

    def test_ledger_route_error_returns_json_500(self):
        state_server.LEDGER_PATH = self.dir
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.req("/ledger", {"addSession": {"minutes": 10}})
        self.assertEqual(ctx.exception.code, 500)
        body = json.loads(ctx.exception.read())
        self.assertIn("error", body)

    def test_concurrent_ledger_writes_both_persist(self):
        def add(text):
            self.req("/ledger", {"addStep": {"courseKey": "applab", "text": text}})

        t1 = threading.Thread(target=add, args=("a",))
        t2 = threading.Thread(target=add, args=("b",))
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        texts = {s["text"] for s in ledger.load(self.ledger)["steps"]["applab"]}
        self.assertEqual(texts, {"a", "b"})


if __name__ == "__main__":
    unittest.main()
