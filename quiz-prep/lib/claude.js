// The AI behind Quiz Prep when there is no class proxy (AI_BASE_URL empty): the student's own
// Claude Code, run headless (`claude -p`). Photos are written to a temp folder and read with Claude's Read tool.
const { execFile } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");

const CANDIDATES = [path.join(os.homedir(), ".local", "bin", "claude"), path.join(os.homedir(), ".claude", "local", "claude"),
  "/opt/homebrew/bin/claude", "/usr/local/bin/claude"];

function claudeBin(env = process.env, exists = fs.existsSync) {
  if (env.CLAUDE_BIN) return env.CLAUDE_BIN;
  for (const dir of (env.PATH || "").split(path.delimiter)) {
    if (dir && exists(path.join(dir, "claude"))) return path.join(dir, "claude");
  }
  return CANDIDATES.find((p) => exists(p)) || null;
}

// data:image/png;base64,... -> a file in dir. Returns the paths written.
function writeImages(images, dir) {
  return images.map((url, i) => {
    const m = /^data:image\/(png|jpe?g|gif|webp|heic);base64,(.+)$/i.exec(String(url));
    if (!m) throw new Error("Photo " + (i + 1) + " is not an image the AI can read.");
    const file = path.join(dir, "photo-" + (i + 1) + "." + m[1].toLowerCase().replace("jpeg", "jpg"));
    fs.writeFileSync(file, Buffer.from(m[2], "base64"));
    return file;
  });
}

function buildArgs(prompt, files, dir) {
  const text = files.length
    ? prompt + "\n\nThe photos are these files; read every one before answering:\n" + files.join("\n")
    : prompt;
  const args = ["-p", text, "--output-format", "text"];
  if (files.length) args.push("--allowedTools", "Read", "--add-dir", dir);
  return args;
}

function askClaude({ prompt, images = [], timeoutMs = 240000, run = execFile, bin = claudeBin() }) {
  if (!bin) return Promise.reject(new Error("No AI set up: install Claude Code (claude.com/claude-code) or set AI_BASE_URL in .env."));
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "quiz-prep-ai-"));
  let files;
  try { files = writeImages(images, dir); } catch (e) { fs.rmSync(dir, { recursive: true, force: true }); return Promise.reject(e); }
  return new Promise((resolve, reject) => {
    run(bin, buildArgs(prompt, files, dir), { timeout: timeoutMs, maxBuffer: 8 * 1024 * 1024, cwd: dir }, (err, stdout, stderr) => {
      fs.rmSync(dir, { recursive: true, force: true });
      if (err) return reject(new Error("Claude did not answer: " + String(stderr || err.message).trim().split("\n").pop()));
      resolve(String(stdout).trim());
    });
  });
}

module.exports = { askClaude, claudeBin, buildArgs, writeImages };
