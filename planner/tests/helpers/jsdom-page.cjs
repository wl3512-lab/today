/* Boot planner.html under jsdom the way a browser would.

   jsdom has no matchMedia and no canvas, and the page's main script uses both
   on boot. Without these the IIFE throws, everything after it never runs, and
   a harness reports a dead handler as a failing feature - which is exactly
   what happened while testing the vitamins row.

   Errors are captured through the virtual console, not a window listener:
   inline scripts run during construction, so a listener added afterwards
   misses every boot-time throw and the page looks clean when it is not. */
const { JSDOM, VirtualConsole } = require("jsdom");
const fs = require("fs");

module.exports = function bootPage(opts) {
  opts = opts || {};
  // the Internships page is loaded from the internship-agent clone with a
  // document.write'd <script src>/<link>; jsdom fetches neither, so inline them
  const path = require("path");
  const beside = path.join(__dirname, "..", "..", "..", "internship-agent", "ui");
  const uiDir = fs.existsSync(beside) ? beside : path.join(require("os").homedir(), "internship-agent", "ui");
  const ui = f => fs.readFileSync(path.join(uiDir, f), "utf8");
  const html = fs.readFileSync(opts.file || require("path").join(__dirname, "..", "..", "planner.html"), "utf8")
    .replace(/<script>document\.write\('<link rel="stylesheet" href="\.\.\/internship-agent\/ui\/internships\.css[^\n]*<\/script>/,
             () => "<style>\n" + ui("internships.css") + "</style>")
    .replace(/<script>document\.write\('<script src="\.\.\/internship-agent\/ui\/internships\.js[^\n]*<\/script>/,
             () => "<script>\n" + ui("internships.js") + "</script>");
  const errors = [];
  const vc = new VirtualConsole();
  vc.on("jsdomError", e => errors.push(String(e.message || e).slice(0, 220)));

  const dom = new JSDOM(html, {
    virtualConsole: vc,
    runScripts: "dangerously",
    // file:// is an opaque origin under jsdom and has no localStorage
    url: "http://localhost/planner.html",
    pretendToBeVisual: true,
    beforeParse(w) {
      // Do not restore a real session from the running planner's storage
      // endpoint when booting an isolated UI fixture.
      w.XMLHttpRequest = function () {
        this.status = 503; this.responseText = "{}";
        this.open = function () {};
        this.send = function () {};
      };
      w.fetch = opts.fetch || (() => Promise.resolve({
        ok: true, json: () => Promise.resolve({}), text: () => Promise.resolve("{}")
      }));
      w.matchMedia = q => ({ matches: false, media: q,
        addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} });
      const ctx = new Proxy({}, {
        get: (t, k) => (k in t ? t[k] : (t[k] = k === "canvas" ? null : () => ctx))
      });
      w.HTMLCanvasElement.prototype.getContext = () => ctx;
    }
  });
  return { dom, window: dom.window, document: dom.window.document, errors };
};
