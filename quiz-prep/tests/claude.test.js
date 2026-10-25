const assert = require("assert");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { askClaude, claudeBin, buildArgs, writeImages } = require("../lib/claude");

(async () => {
  // finds claude on PATH first, then the usual install spots; CLAUDE_BIN wins over both
  const seen = new Set(["/x/bin/claude", path.join(os.homedir(), ".local", "bin", "claude")]);
  assert.strictEqual(claudeBin({ PATH: "/nope:/x/bin" }, (p) => seen.has(p)), "/x/bin/claude");
  assert.strictEqual(claudeBin({ PATH: "/nope" }, (p) => seen.has(p)), path.join(os.homedir(), ".local", "bin", "claude"));
  assert.strictEqual(claudeBin({ PATH: "", CLAUDE_BIN: "/my/claude" }, () => false), "/my/claude");
  assert.strictEqual(claudeBin({ PATH: "" }, () => false), null);

  // text only: no tools, no extra folder
  assert.deepStrictEqual(buildArgs("hi", [], "/d"), ["-p", "hi", "--output-format", "text"]);
  // photos: their paths are named in the prompt and only Read is allowed, inside the temp folder
  const a = buildArgs("read this quiz", ["/d/photo-1.png"], "/d");
  assert.ok(a[1].includes("/d/photo-1.png") && a.includes("Read") && a[a.indexOf("--add-dir") + 1] === "/d");

  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "qp-test-"));
  const files = writeImages(["data:image/png;base64," + Buffer.from("PNG!").toString("base64")], dir);
  assert.strictEqual(fs.readFileSync(files[0], "utf8"), "PNG!");
  assert.throws(() => writeImages(["https://example.com/x.png"], dir), /not an image/);
  fs.rmSync(dir, { recursive: true, force: true });

  // a fake claude: answer comes back trimmed, and the temp folder is gone afterwards
  let usedDir;
  const out = await askClaude({ prompt: "2+2?", images: ["data:image/jpeg;base64,AAAA"], bin: "/fake/claude",
    run: (bin, args, opts, cb) => { usedDir = opts.cwd; assert.ok(fs.existsSync(path.join(usedDir, "photo-1.jpg"))); cb(null, " 4 \n", ""); } });
  assert.strictEqual(out, "4");
  assert.ok(!fs.existsSync(usedDir));

  await assert.rejects(askClaude({ prompt: "x", bin: null }), /install Claude Code/);
  await assert.rejects(askClaude({ prompt: "x", bin: "/fake", run: (b, a, o, cb) => cb(new Error("boom"), "", "rate limited\n") }), /rate limited/);
  console.log("claude ok");
})().catch((e) => { console.error(e); process.exit(1); });
