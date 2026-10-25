"""Personal extras, loaded only when the profile lists them.

A plugin is a module found in planner/personal/ or ~/.today/plugins/. It may
offer any of:
  POST_ROUTES = {path: fn(body) -> dict}   extra server routes
  handle_get(handler) -> bool             answer a GET itself (True = handled)
  fetch_items(course, errors) -> [items]  extra deadlines for a course during sync
  KEYED_ROUTES = (path prefixes,)          routes that need the planner's key (agents with shell access)
  READ_ROOTS = [folders]                  folders the planner window may also read files from
The core never imports a plugin by name, so it runs the same without any.
Core features that come as plugins (the internship agent) load when the
profile's "features" lists them: names_for(profile).
"""
import importlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SEARCH = (os.path.join(HERE, "personal"), os.path.expanduser("~/.today/plugins"))
_loaded = {}
# feature name -> the core plugin that brings it
FEATURE_PLUGINS = {"internships": "internships_plugin"}


def names_for(p):
    """The plugins a profile asks for: its own list, then the plugins behind its features."""
    names = list(p.get("plugins") or [])
    for feature in p.get("features") or []:
        mod = FEATURE_PLUGINS.get(feature)
        if mod and mod not in names:
            names.append(mod)
    return names


def load(names, search=SEARCH):
    for d in search:
        if os.path.isdir(d) and d not in sys.path:
            sys.path.insert(0, d)
    for name in names or []:
        if name in _loaded:
            continue
        try:
            _loaded[name] = importlib.import_module(name)
        except Exception as exc:   # a broken or missing extra must never stop the planner
            sys.stderr.write("[Today] plugin %s not loaded: %r\n" % (name, exc))
    return dict(_loaded)


def get(name):
    return _loaded.get(name)


def loaded():
    return list(_loaded.values())


def reset():
    _loaded.clear()


def post_routes():
    out = {}
    for mod in loaded():
        out.update(getattr(mod, "POST_ROUTES", {}) or {})
    return out


def keyed_routes():
    out = []
    for mod in loaded():
        out += list(getattr(mod, "KEYED_ROUTES", ()) or ())
    return out


def read_roots():
    """Extra folders the planner window may read (e.g. a plugin's own page files)."""
    out = []
    for mod in loaded():
        out += [p for p in (getattr(mod, "READ_ROOTS", ()) or ()) if p]
    return out


def handle_get(handler):
    for mod in loaded():
        hook = getattr(mod, "handle_get", None)
        if hook and hook(handler):
            return True
    return False


def course_items(course, errors):
    out = []
    for mod in loaded():
        fetch = getattr(mod, "fetch_items", None)
        if fetch:
            out += fetch(course, errors) or []
    return out
