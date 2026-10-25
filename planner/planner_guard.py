"""Keep the planner's browser to one page: the planner.

The planner runs in its own Chrome instance (profile ~/.today-planner-chrome).
macOS knows it only as "Google Chrome", so whenever her real Chrome is not
running, a link clicked in any other app lands in the planner's instance as a
new tab - Google sign-ins, QuillBot, Notion, and the planner itself dozens of
times over, all in the one browser that was meant to hold a single page.

The planner's Chrome is started with a DevTools port on localhost. Every few
seconds the menubar asks it for its pages and applies `decide`: the planner
page stays (one of it), anything else is closed and its url handed to her
real Chrome, where she meant it to go.
"""
import json
import urllib.request

PORT = 9311
GRACE = 2          # polls a blank page may live: a link opens as about:blank first


def is_planner(url, page_name):
    return url.startswith("file://") and page_name in url


def decide(targets, page_name, blank_seen=None):
    """(ids to close, urls to reopen in her real Chrome, updated blank_seen).

    targets: DevTools /json rows. Only type "page" counts - workers,
    iframes and the like are Chrome's own business. Of several planner pages
    the last listed is kept (Chrome lists newest first, so that is the one
    she has had open longest).
    """
    blank_seen = dict(blank_seen or {})
    pages = [t for t in targets if t.get("type") == "page"]
    close, forward, still_blank = [], [], {}
    planners = [t for t in pages if is_planner(t.get("url", ""), page_name)]
    for t in planners[:-1]:
        close.append(t["id"])
    for t in pages:
        url = t.get("url", "")
        if is_planner(url, page_name):
            continue
        if url.startswith(("http://", "https://", "file://")):
            close.append(t["id"])
            forward.append(url)
        elif url in ("", "about:blank") or url.startswith("chrome://newtab"):
            # a link mid-open, or Cmd+T: give it a moment to become a url
            n = blank_seen.get(t["id"], 0) + 1
            if n > GRACE:
                close.append(t["id"])
            else:
                still_blank[t["id"]] = n
        else:
            # chrome://settings, extensions, devtools: nothing to forward
            close.append(t["id"])
    return close, forward, still_blank


def _get(path, timeout=0.5):
    with urllib.request.urlopen("http://127.0.0.1:%d%s" % (PORT, path), timeout=timeout) as r:
        return r.read()


def targets():
    """The planner Chrome's pages, or None when it is not running with the port."""
    try:
        return json.loads(_get("/json/list"))
    except Exception:
        return None


def close(target_id):
    try:
        _get("/json/close/" + target_id)
        return True
    except Exception:
        return False


class Guard:
    """One poll per call; the menubar runs it on a timer."""

    def __init__(self, page_name, forward_urls):
        self.page_name = page_name
        self.forward_urls = forward_urls
        self.blank_seen = {}

    def poll(self):
        rows = targets()
        if rows is None:
            self.blank_seen = {}
            return None
        ids, urls, self.blank_seen = decide(rows, self.page_name, self.blank_seen)
        if urls:
            self.forward_urls(urls)
        for i in ids:
            close(i)
        return ids, urls
