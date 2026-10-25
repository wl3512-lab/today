// Browser code. It never sees the API token.
const EMBED = new URLSearchParams(location.search).has("embed");
// The course's own labels (its code and name, the worksheet header) come from its settings, via /api/health.
let COURSE_LABELS = {};
fetch("/api/health").then((r) => r.json()).then((h) => {
  COURSE_LABELS = h.course || {};
  const note = document.getElementById("brand-note"); if (note) note.textContent = COURSE_LABELS.label || "";
}).catch(() => {});
if (EMBED) document.documentElement.classList.add("embed");
// Tell Today how tall the page is so its frame fits without a scrollbar.
if (EMBED && window.parent !== window) {
  new ResizeObserver(() => parent.postMessage({ quizPrepHeight: document.documentElement.scrollHeight }, "*")).observe(document.body);
}
const tabs = document.querySelectorAll('[role="tab"]');
function openTab(name) {
  tabs.forEach((t) => { const on = t.dataset.tab === name; t.setAttribute("aria-selected", String(on)); t.tabIndex = on ? 0 : -1; });
  document.querySelectorAll('[role="tabpanel"]').forEach((panel) => { panel.hidden = panel.id !== name; });
  if (location.hash.slice(1).split("/")[0] !== name) history.replaceState(null, "", "#" + name);
}
tabs.forEach((tab, i) => {
  tab.addEventListener("click", () => openTab(tab.dataset.tab));
  tab.addEventListener("keydown", (e) => {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    const next = tabs[(i + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length];
    next.focus(); openTab(next.dataset.tab);
  });
});
const startTab = location.hash.slice(1).split("/")[0];   // "#kit/quiz/review" opens the kit tab; the kit router picks the page
if ([...tabs].some((t) => t.dataset.tab === startTab)) openTab(startTab);

// ── Step 4: photo upload + preview ──
const photoInput = document.getElementById("photo-input");
const preview = document.getElementById("preview");
const uploadError = document.getElementById("upload-error");
window.selectedPhotos = []; // used by the Extract step later

photoInput.addEventListener("change", () => {
  preview.innerHTML = "";
  uploadError.textContent = "";
  window.selectedPhotos = [];
  const files = Array.from(photoInput.files);
  const bad = files.filter((f) => !["image/jpeg", "image/png"].includes(f.type));
  if (bad.length) {
    uploadError.textContent = "Please upload a JPG or PNG. Not accepted: " + bad.map((f) => f.name).join(", ");
    photoInput.value = "";
    return;
  }
  Promise.all(files.map((file) => new Promise((ok) => {
    const reader = new FileReader();
    reader.onload = () => ok({ name: file.name, dataUrl: reader.result });
    reader.readAsDataURL(file);
  }))).then(showPhotos);
});

function showPhotos(photos) {
  window.selectedPhotos = photos;
  preview.innerHTML = "";
  photos.forEach((p, i) => {
    const fig = document.createElement("figure");
    const img = document.createElement("img");
    img.src = p.dataUrl;
    img.alt = "Quiz page " + (i + 1);
    const cap = document.createElement("figcaption");
    cap.textContent = "Page " + (i + 1) + ": " + p.name;
    fig.append(img, cap);
    preview.append(fig);
  });
  document.getElementById("extract-btn").disabled = !photos.length;
}

document.getElementById("use-saved").addEventListener("click", async () => {
  uploadError.textContent = "";
  const names = await (await fetch("/api/photos")).json();
  if (!names.length) { uploadError.textContent = "data/photos is empty."; return; }
  const photos = await Promise.all(names.map(async (name) => {
    const blob = await (await fetch("/photos/" + encodeURIComponent(name))).blob();
    return new Promise((ok) => { const r = new FileReader(); r.onload = () => ok({ name, dataUrl: r.result }); r.readAsDataURL(blob); });
  }));
  showPhotos(photos);
});

// ── Step 5: extract with AI ──
const form = document.getElementById("profile-form");
const qList = document.getElementById("q-list");
const esc = (t) => String(t ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

document.getElementById("extract-btn").addEventListener("click", async (e) => {
  const btn = e.currentTarget, status = document.getElementById("extract-status");
  btn.disabled = true; status.textContent = "Reading your quiz… (about 20 seconds)"; uploadError.textContent = "";
  try {
    const r = await fetch("/api/extract", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ photos: window.selectedPhotos }) });
    const data = await r.json();
    if (!r.ok) throw new Error(data.error);
    fillForm(data); status.textContent = "Done. Check every box below, then save.";
  } catch (err) {
    uploadError.textContent = err.message || "Extraction failed."; status.textContent = "";
  } finally { btn.disabled = false; }
});

function fillForm(p) {
  window.currentProfile = p;
  form.hidden = false;
  form.title.value = p.format?.title || "";
  form.instructions.value = p.format?.instructions || "";
  form.topics.value = p.topics || "";
  form.difficulty.value = p.difficulty || "medium";
  form.showWork.checked = !!p.format?.showWork;
  form.calculatorAllowed.checked = !!p.format?.calculatorAllowed;
  qList.innerHTML = p.questions.map((q, i) => `
    <fieldset class="q" data-i="${i}">
      <legend>Question ${q.number}</legend>
      <div class="row">
        <label>Type <select name="type">
          ${["multiple_choice", "short_answer", "show_work"].map((t) => `<option ${t === q.type ? "selected" : ""}>${t}</option>`).join("")}
        </select></label>
        <label>Points <input name="points" type="number" min="0" step="0.5" value="${q.points}"></label>
      </div>
      <label>Question text <textarea name="text" rows="3">${esc(q.text)}</textarea></label>
      <label>Choices (one per line) <textarea name="choices" rows="3">${esc(q.choices.join("\n"))}</textarea></label>
      <label>Parts (one per line: label | points | text) <textarea name="parts" rows="3">${esc(q.parts.map((x) => [x.label, x.points, x.text].join(" | ")).join("\n"))}</textarea></label>
    </fieldset>`).join("");
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const status = document.getElementById("save-status");
  const base = window.currentProfile || {};
  const questions = [...qList.querySelectorAll(".q")].map((fs, i) => ({
    number: i + 1,
    type: fs.querySelector("[name=type]").value,
    points: Number(fs.querySelector("[name=points]").value) || 0,
    text: fs.querySelector("[name=text]").value.trim(),
    choices: fs.querySelector("[name=choices]").value.split("\n").map((s) => s.trim()).filter(Boolean),
    parts: fs.querySelector("[name=parts]").value.split("\n").map((s) => s.trim()).filter(Boolean).map((line) => {
      const [label, pts, ...rest] = line.split("|").map((x) => x.trim());
      return { label, points: Number(pts) || 0, text: rest.join(" | ") };
    })
  }));
  const profile = {
    sourcePhotos: base.sourcePhotos || [],
    format: { title: form.title.value.trim(), instructions: form.instructions.value.trim(),
      calculatorAllowed: form.calculatorAllowed.checked, showWork: form.showWork.checked },
    topics: form.topics.value.trim(), difficulty: form.difficulty.value, questions
  };
  const r = await fetch("/api/profiles", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(profile) });
  const data = await r.json();
  status.textContent = r.ok ? "Saved to " + data.saved : (data.error || "Couldn't save.");
});

// ── Today planner: next quiz + slides ──
async function loadPlanner() {
  const box = document.getElementById("next-quiz");
  try {
    const r = await fetch("/api/planner");
    const data = await r.json();
    if (!r.ok) throw new Error(data.error);
    if (!data.quizzes.length) { box.innerHTML = "<p>No upcoming quizzes found.</p>"; return; }
    const fmt = (iso) => new Date(new Date(iso).getTime() - 60000)
      .toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
    window.planner = data;
    const [next, ...rest] = data.quizzes;
    window.nextQuiz = next; // the generator will use next.lessons as topics
    const slides = next.slides.length
      ? "<ul>" + next.slides.map((s) => `<li><a href="${encodeURI(s.url)}" target="_blank" rel="noopener">${s.title}</a></li>`).join("") + "</ul>"
      : "<p class='muted'>No annotated slides posted yet for these lessons.</p>";
    box.innerHTML = `
      <h3>Next up: ${next.title} · ${fmt(next.due)}</h3>
      ${next.gist ? `<p>${next.gist}</p>` : ""}
      <h4>Annotated slides (Brightspace)</h4>${slides}
      <details><summary>Later quizzes and exams</summary><ul>
        ${rest.map((q) => `<li>${q.title} · ${fmt(q.due)}</li>`).join("")}
      </ul></details>`;
  } catch (err) {
    box.innerHTML = `<p class="error">${err.message || "Couldn't load your schedule."}</p>`;
  }
}
loadPlanner();

// ── Step 7 + 8: practice quiz with answer key ──
async function loadProfiles() {
  const sel = document.getElementById("profile-select");
  const list = await (await fetch("/api/profiles")).json();
  sel.innerHTML = list.length
    ? list.map((p) => `<option value="${p.id}">${esc(p.format?.title || p.id)} (${p.length} questions, ${p.totalPoints} pts)</option>`).join("")
    : "<option value=''>No saved profiles yet. Save one on Upload Quiz.</option>";
}
loadProfiles();
document.querySelector('[data-tab="practice"]').addEventListener("click", loadProfiles);

// Pre-fill topics from Today planner once it loads
const topicsBox = document.getElementById("topics");
const fillTopics = setInterval(() => {
  if (window.nextQuiz && !topicsBox.value) {
    const g = window.nextQuiz.gist.match(/covers (.+?), due/);
    topicsBox.value = g ? g[1].replace(/Lesson \d+ – /g, "") : "Lessons " + window.nextQuiz.lessons.join(", ");
    clearInterval(fillTopics);
  }
}, 500);
setTimeout(() => clearInterval(fillTopics), 15000);

document.getElementById("gen-btn").addEventListener("click", async (e) => {
  const btn = e.currentTarget, status = document.getElementById("gen-status"), err = document.getElementById("gen-error");
  btn.disabled = true; err.textContent = ""; status.textContent = "Writing and checking your practice quiz… (about 1 minute)";
  try {
    const r = await fetch("/api/practice", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ profileId: document.getElementById("profile-select").value, topics: topicsBox.value, slides: chosenSlides(), lessons: window.nextQuiz?.lessons || [] }) });
    const quiz = await r.json();
    if (!r.ok) throw new Error(quiz.error);
    renderPractice(quiz); status.textContent = "Saved to data/practice/" + quiz.id + ".json";
  } catch (x) { err.textContent = x.message || "Couldn't make a quiz."; status.textContent = ""; }
  finally { btn.disabled = false; }
});

function renderPractice(q) {
  const ans = (a, flag, why) => (a ? `<div class="answer"><strong>Answer:</strong> ${esc(a)}${why ? `<br><span class="sol"><strong>Why:</strong> ${esc(why)}</span>` : ""}</div>` : "") +
    (flag ? `<div class="answer flag"><strong>Double-check this one.</strong> ${esc(flag)}</div>` : "");
  // "text A) x B) y" -> text plus a proper list of choices
  const splitOpts = (t) => {
    const m = String(t).split(/\s(?=[A-F]\)\s)/);
    return m.length > 2 ? { text: m[0], opts: m.slice(1) } : { text: t, opts: [] };
  };
  const optList = (o) => o.length ? `<ul class="choices">${o.map((c) => `<li>${esc(c)}</li>`).join("")}</ul>` : "";
  const flagged = q.questions.reduce((n, x) => n + (x.flag ? 1 : 0) + x.parts.filter((p) => p.flag).length, 0);
  document.getElementById("practice-quiz").innerHTML = `
    <header class="paper-head"><span>Practice</span><span>${esc(q.topics)}</span></header>
    <h2>${esc(q.title)}</h2>
    ${q.instructions ? `<p><em>${esc(q.instructions)}</em></p>` : ""}
    <p class="muted">${q.totalPoints} points</p>
    <p class="check-note no-print">${q.checked === false ? "The answer checker couldn't run this time." :
      flagged ? flagged + " answer" + (flagged === 1 ? "" : "s") + " flagged by the checker. Look at those carefully when you show answers." : "Answer checker agreed with every answer."}</p>
    <ol class="questions">${q.questions.map((x) => `
      <li><p><strong>(${x.points} point${x.points === 1 ? "" : "s"})</strong> ${esc(x.text)}</p>
        ${x.choices.length ? `<ul class="choices">${x.choices.map((c) => `<li>${esc(c)}</li>`).join("")}</ul>` : ""}
        ${x.parts.map((p) => { const s = splitOpts(p.text); return `<div class="part"><p><strong>${esc(p.label)} (${p.points} pt${p.points === 1 ? "" : "s"})</strong> ${esc(s.text)}</p>
          ${optList(s.opts)}${x.type === "show_work" ? '<div class="work-space"></div>' : ""}${ans(p.answer, p.flag, p.why)}</div>`; }).join("")}
        ${ans(x.answer, x.flag, x.why)}
      </li>`).join("")}</ol>`;
  document.getElementById("practice-out").hidden = false;
  setAnswers(false);
}

const answersBtn = document.getElementById("answers-btn");
function setAnswers(on) {
  document.getElementById("practice-quiz").classList.toggle("show-answers", on);
  answersBtn.setAttribute("aria-pressed", String(on));
  answersBtn.textContent = on ? "Hide answers" : "Show answers";
}
answersBtn.addEventListener("click", () => setAnswers(answersBtn.getAttribute("aria-pressed") !== "true"));
// Today shows this app in a web view that ignores window.print(), so there the
// paper opens in her real browser and prints from there.
function printPaper(paper, title) {
  if (!EMBED) return window.print();
  const id = Date.now().toString(36) + Math.random().toString(36).slice(2, 10);
  fetch("/api/print", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id, title, html: paper.outerHTML }) });
  window.open(location.origin + "/print/" + id, "_blank");
}
document.getElementById("print-btn").addEventListener("click", () => printPaper(document.getElementById("practice-quiz"), "Practice quiz"));


// ── Slides: read PDF text in the browser, save it locally ──
if (window.pdfjsLib) pdfjsLib.GlobalWorkerOptions.workerSrc = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";
async function loadSlides() {
  const list = await (await fetch("/api/slides")).json();
  const box = document.getElementById("slide-list");
  const wanted = (window.nextQuiz?.lessons || []);
  box.innerHTML = list.length ? list.map((s) => {
    const on = wanted.some((n) => new RegExp("Lesson " + n + "\\b", "i").test(s.name));
    return `<label class="check"><input type="checkbox" name="slide" value="${esc(s.name)}" ${on ? "checked" : ""}> ${esc(s.name)}</label>`;
  }).join("") : "None added yet.";
}
const chosenSlides = () => [...document.querySelectorAll("input[name=slide]:checked")].map((c) => c.value);
setTimeout(loadSlides, 1500);

document.getElementById("slide-input").addEventListener("change", async (e) => {
  const file = e.target.files[0], status = document.getElementById("slide-status");
  if (!file) return;
  if (!window.pdfjsLib) { status.textContent = "Couldn't load the PDF reader. Check your internet connection."; return; }
  status.textContent = "Reading " + file.name + "…";
  try {
    const pdf = await pdfjsLib.getDocument({ data: await file.arrayBuffer() }).promise;
    let text = "";
    for (let i = 1; i <= pdf.numPages; i++) {
      const c = await (await pdf.getPage(i)).getTextContent();
      text += "\n[slide " + i + "] " + c.items.map((it) => it.str).join(" ");
    }
    const r = await fetch("/api/slides", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: file.name, text }) });
    const d = await r.json();
    if (!r.ok) throw new Error(d.error);
    status.textContent = "Added " + d.saved + " (" + pdf.numPages + " slides).";
    await loadSlides();
    const box = [...document.querySelectorAll("input[name=slide]")].find((c) => c.value === d.saved);
    if (box) box.checked = true;
  } catch (x) { status.textContent = x.message || "Couldn't read that PDF."; }
  e.target.value = "";
});

// ── Step 9: score log ──
const scoreForm = document.getElementById("score-form");
scoreForm.date.value = new Date().toLocaleDateString("en-CA");
function drawScores(manual) {
  const g = window.planner?.grades;
  const qz = g?.categories?.find((c) => /quiz/i.test(c.name));
  const bs = (qz?.items || []).map((it) => ({ quiz: it.name, score: it.points, outOf: it.outOf, src: "Brightspace" }));
  const names = new Set(bs.map((x) => x.quiz.toLowerCase()));
  const list = [...bs, ...manual.filter((m) => !names.has(String(m.quiz).toLowerCase())).map((m) => ({ ...m, src: "you" }))];
  drawBrightspace(g, qz);
  const tbody = document.querySelector("#score-table tbody");
  tbody.innerHTML = list.length ? list.map((s) => `<tr><td>${s.date || "Brightspace"}</td><td>${esc(s.quiz)}</td><td>${s.score} / ${s.outOf}</td>
    <td>${Math.round(100 * s.score / s.outOf)}%</td>
    <td>${s.id ? `<button type="button" class="secondary small" data-del="${s.id}" aria-label="Remove ${esc(s.quiz || s.date)}">Remove</button>` : ""}</td></tr>`).join("")
    : "<tr><td colspan='5' class='muted'>No scores yet. Add your first real quiz score above.</td></tr>";
  const chart = document.getElementById("score-chart");
  if (list.length < 2) { chart.innerHTML = ""; return; }
  const W = 600, H = 180, pad = 28, pts = list.map((s, i) => [pad + i * (W - 2 * pad) / (list.length - 1), H - pad - (s.score / s.outOf) * (H - 2 * pad)]);
  chart.innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Quiz scores over time">
    ${[0, 50, 100].map((v) => { const y = H - pad - v / 100 * (H - 2 * pad); return `<line x1="${pad}" x2="${W - pad}" y1="${y}" y2="${y}" class="grid"/><text x="2" y="${y + 4}" class="axis">${v}%</text>`; }).join("")}
    <polyline points="${pts.map((p) => p.join(",")).join(" ")}" class="line"/>
    ${pts.map((p, i) => `<circle cx="${p[0]}" cy="${p[1]}" r="4" class="dot"><title>${esc(list[i].quiz)}: ${list[i].score}/${list[i].outOf}</title></circle>`).join("")}</svg>`;
}
let manualScores = [];
(async () => {
  for (let i = 0; i < 30 && !window.planner; i++) await new Promise((r) => setTimeout(r, 300));
  manualScores = await (await fetch("/api/scores")).json();
  drawScores(manualScores);
})();

function drawBrightspace(g, qz) {
  const box = document.getElementById("bs-scores");
  if (!g) { box.innerHTML = "<p class='muted'>Open the Today app to see your Brightspace grades.</p>"; return; }
  const pts = (qz?.items || []).map((x) => x.points / x.outOf);
  const kept = [...pts].sort((a, b) => b - a).slice(0, Math.max(pts.length - (qz?.drops || 0), 1));
  const keptAvg = kept.length ? Math.round(100 * kept.reduce((a, b) => a + b, 0) / kept.length) : null;
  box.innerHTML = `<h3>Quizzes from Brightspace</h3>
    <p>${qz?.items.length || 0} graded · average <strong>${qz?.pct ?? "?"}%</strong>.
    Your ${qz?.drops || 0} lowest are dropped at the end${keptAvg !== null && pts.length > (qz?.drops || 0) ? `, so right now your best counts average <strong>${keptAvg}%</strong>` : ""}.</p>
    <p class="muted small">Synced ${new Date(g.updated).toLocaleString()} by Today planner.</p>`;
}
scoreForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const err = document.getElementById("score-error"); err.textContent = "";
  const r = await fetch("/api/scores", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(Object.fromEntries(new FormData(scoreForm))) });
  const d = await r.json();
  if (!r.ok) { err.textContent = d.error; return; }
  manualScores = d; drawScores(d); scoreForm.score.value = ""; scoreForm.quiz.value = "";
});
document.getElementById("score-table").addEventListener("click", async (e) => {
  const id = e.target.dataset?.del; if (!id) return;
  manualScores = await (await fetch("/api/scores/" + id, { method: "DELETE" })).json(); drawScores(manualScores);
});


// ── Study Kit ──
const kitHead = document.getElementById("kit-head"), kitMats = document.getElementById("kit-mats");
const kitBody = document.getElementById("kit-body");
const fmtDay = (iso) => new Date(new Date(iso).getTime() - 60000).toLocaleDateString(undefined, { weekday: "long", month: "short", day: "numeric" });
const daysLeft = (iso) => Math.ceil((new Date(iso) - Date.now()) / 86400000);

// pick = a later quiz chosen in Build settings (a copy, so the schedule itself isn't changed); default is the next quiz
async function initKit(pick) {
  // wait for the planner data loaded by the Practice tab code
  for (let i = 0; i < 30 && !window.nextQuiz; i++) await new Promise((r) => setTimeout(r, 300));
  const q = pick || { ...window.nextQuiz, lessons: [...(window.nextQuiz?.lessons || [])] };
  if (!q) { kitHead.innerHTML = "<p class='error'>Couldn't find your next quiz. Open the Today app, then refresh.</p>"; return; }
  let topic = (q.gist.match(/covers (.+?), due/) || [])[1] || "Lessons " + q.lessons.join(", ");
  const qn = Number((q.title.match(/Quiz\s*(\d+)/i) || [])[1]);
  const ann = qn ? await (await fetch("/api/announced?n=" + qn)).json() : null;
  let note = `<p class="muted small">From the course schedule. Not yet confirmed in class slides.</p>`;
  if (ann) {
    topic = ann.topics;
    if (ann.lessons.length) q.lessons = ann.lessons;
    note = `<p class="muted small">✓ Confirmed by your professor in <em>${esc(ann.source)}</em>${ann.when ? " (" + esc(ann.when) + ")" : ""}. The schedule sheet said Lessons ${esc((q.title.match(/\(([^)]*)\)/) || [])[1] || "")}.</p>`;
    if (topicsBox) topicsBox.value = topic;
  }
  if (!pick && window.nextQuiz) window.nextQuiz.lessons = q.lessons;   // the practice quiz generator studies these
  const d = daysLeft(q.due);
  kitHead.innerHTML = `<h3>${esc(ann ? q.title.replace(/\s*\(.*\)$/, "") : q.title)} · ${fmtDay(q.due)} <span class="pill">${d <= 0 ? "today" : d === 1 ? "tomorrow" : "in " + d + " days"}</span></h3>
    <p><strong>On the quiz:</strong> ${esc(topic)}</p>${note}`;
  const mats = await (await fetch("/api/materials")).json();
  const saved = await (await fetch("/api/kit?quiz=" + encodeURIComponent(q.title))).json();
  // Which lessons the kit studies: her last build's choice, else the quiz's (confirmed) lessons. She can tick others,
  // since the schedule's quiz numbers are lecture numbers (Quiz 7 "(12, 13)" is Lessons 9 and 10).
  const chosen = saved?.lessons?.length ? saved.lessons : q.lessons;
  const lessonsHere = [...new Map(mats.filter((m) => m.kind === "slides").map((m) => [m.number, m])).values()].sort((a, b) => b.number - a.number);
  const titleOf = (m) => m.name.replace(/^.*Lesson\s*\d+\s*[-–]\s*/i, "").replace(/\s*Part\s+[IVX\d]+.*$|\s*Annotated.*$/i, "");
  const missing = chosen.filter((n) => !lessonsHere.some((m) => m.number === n));
  const sheets = mats.filter((m) => m.kind === "worksheet");
  const newest = sheets.length ? Math.max(...sheets.map((m) => m.number)) : -1;
  kitMats.innerHTML = `<h4>Lessons to study</h4>
    <p class="muted small">Ticked from the quiz's topics. Change them if the quiz covers other lessons, then Rebuild.</p>
    ${lessonsHere.length ? lessonsHere.map((m) => `<label class="check"><input type="checkbox" name="lesson" value="${m.number}" ${chosen.includes(m.number) ? "checked" : ""}> Lesson ${m.number} · ${esc(titleOf(m))}</label>`).join("") : "<p class='muted'>No lesson slides in Downloads yet.</p>"}
    ${missing.length ? `<p class="warn">Missing: Lesson ${missing.join(", ")}. ${q.slides.length ? "Download from Brightspace: " + q.slides.map((s) => `<a href="${encodeURI(s.url)}" target="_blank" rel="noopener">${esc(s.title)}</a>`).join(", ") + ", then click Build again." : "Not posted on Brightspace yet."}</p>` : ""}
    <h4>Worksheets to copy the style of</h4>
    ${sheets.length ? sheets.map((m) => `<label class="check"><input type="checkbox" name="ws" value="${esc(m.name)}" ${m.number >= newest - 1 ? "checked" : ""}> ${esc(m.name)}</label>`).join("") : "<p class='muted'>No worksheets for this course in Downloads.</p>"}`;
  window.kitInfo = { quiz: q.title, lessons: chosen, topics: chosen.join() === q.lessons.join() ? topic : saved?.topics || topic };
  kitMats.onchange = (e) => {
    if (e.target.name !== "lesson") return;
    const picked = [...kitMats.querySelectorAll("input[name=lesson]:checked")].map((c) => Number(c.value)).sort((a, b) => a - b);
    window.kitInfo.lessons = picked;
    window.kitInfo.topics = picked.join() === q.lessons.join() ? topic
      : picked.map((n) => titleOf(lessonsHere.find((m) => m.number === n))).join(", ");
    // The kit belongs to this quiz: studying other lessons for it would replace its kit (that's how Quiz 6 lost Lesson 8 once).
    const warn = document.getElementById("kit-lesson-warn");
    const off = ann?.lessons?.length && !ann.lessons.every((n) => picked.includes(n));
    warn.hidden = !off;
    if (off) warn.textContent = `Your professor confirmed ${quizName()} covers Lesson ${ann.lessons.join(", ")}. Rebuilding with other lessons replaces this kit. To get ready for a later quiz, pick it in "Build a kit for" above instead.`;
  };
  // which quiz this kit is for: the next one, or a later one she wants to start on early
  const quizzes = (window.planner?.quizzes || []).filter((x) => /^Quiz/i.test(x.title));
  const qsel = document.getElementById("kit-quiz");
  qsel.innerHTML = quizzes.map((x) => `<option value="${esc(x.title)}" ${x.title === q.title ? "selected" : ""}>${esc(x.title.replace(/\s*\(.*\)$/, ""))} · ${fmtDay(x.due)}</option>`).join("");
  qsel.onchange = () => {
    const x = quizzes.find((y) => y.title === qsel.value);
    if (!x || x.title === window.nextQuiz?.title) { document.getElementById("kit-mode").hidden = true; initKit(); return; }
    showKitMode(x.title); initKit({ ...x, lessons: [...x.lessons] });
  };
  drawResume();   // now it can say "Quiz 6 · Worksheet" instead of "Quiz · Worksheet"
  drawMath();
  if (saved) { renderKit(saved); document.getElementById("kit-btn").textContent = "Rebuild study kit"; }
  else {   // no kit for this quiz yet: clear the last one off the pages
    window.currentKit = null; kitBody.hidden = true; document.getElementById("ready").innerHTML = "";
    document.getElementById("quiz-links").hidden = true; document.getElementById("kit-btn").textContent = "Build study kit";
    document.getElementById("quiz-empty").hidden = false; document.getElementById("quiz-none").hidden = false;
  }
}
initKit();

document.getElementById("kit-btn").addEventListener("click", async (e) => {
  const btn = e.currentTarget, st = document.getElementById("kit-status"), err = document.getElementById("kit-error");
  btn.disabled = true; err.textContent = ""; st.textContent = "Reading your slides and building the kit… (about 1 minute)";
  try {
    const r = await fetch("/api/kit", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...window.kitInfo, worksheets: [...document.querySelectorAll("input[name=ws]:checked")].map((c) => c.value) }) });
    const kit = await r.json();
    if (!r.ok) throw new Error(kit.error);
    renderKit(kit); st.textContent = "Built. Saved for this quiz, so it loads instantly next time."; btn.textContent = "Rebuild study kit";
    showKitPage("quiz/plan");
  } catch (x) { err.textContent = x.message || "Couldn't build the kit."; st.textContent = ""; }
  finally { btn.disabled = false; }
});

document.querySelector(".subtabs").addEventListener("click", (e) => {
  const sub = e.target.dataset?.sub; if (sub) showKitPage("quiz/" + sub);
});
document.getElementById("go-test").addEventListener("click", () => document.querySelector('[data-tab="practice"]').click());

let progress = {};
const saveProgress = (patch) => {
  Object.assign(progress, patch);
  drawReady();
  return fetch("/api/progress", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ quiz: window.kitInfo.quiz, patch }) });
};

function planSteps(due) {
  // The quiz is in Friday recitation, so finish studying the day before.
  const d = Math.max(daysLeft(due) - 1, 1);
  const all = Ready.READY_STEPS;   // public/ready.js: the same 8 steps the Ready % counts
  // spread over the days left: today gets what fits
  const per = Math.ceil(all.length / d);
  return all.map((s, i) => ({ ...s, day: Math.min(Math.floor(i / per), d - 1) }));
}

function drawReady() {
  const k = window.currentKit; if (!k) return;
  const r = Ready.readiness(progress, k);
  // steps that ticked themselves stay ticked, so a new worksheet (which clears the marks) can't lower the %
  const plan = progress.plan || {}, newly = [...r.doneIds].filter((id) => !plan[id]);
  if (newly.length) { saveProgress({ plan: { ...plan, ...Object.fromEntries(newly.map((id) => [id, true])) } }); return; }
  document.getElementById("ready").innerHTML = r.pct === 100
    ? `<div class="ready-row done"><span class="ready-ring full" role="img" aria-label="100% ready"><span>100%</span></span>
        <p><strong>You're ready for ${esc(quizName())} 🎉</strong><br><span class="muted small">All ${r.total} steps done.</span></p></div>`
    : `<button type="button" class="ready-row ready-go" id="ready-go">
        <span class="ready-ring" role="img" aria-label="${r.pct}% ready" style="--pct:${r.pct}"><span>${r.pct}%</span></span>
        <span class="ready-text"><strong>Get me to 100% →</strong><span class="muted small">${r.done} of ${r.total} steps done · next: ${esc(r.next.label)}</span></span></button>`;
  const go = document.getElementById("ready-go"); if (go) go.onclick = startGuide;
  drawGuide();
}

// Why a worksheet problem is there (from her ✓/✗ marks on the last sheet).
const focusTag = (f) => f === "missed" ? `<span class="focus-tag missed">🔁 Missed last time</span>`
  : f === "kept" ? `<span class="focus-tag kept">✓ Keeping it fresh</span>` : "";
// The answer checker solved it differently: show both, so a wrong key never makes her mark a right answer ✗.
const wsFlag = (f) => f ? `<span class="ws-flag"><strong>Double-check this one.</strong> ${esc(f)}</span>` : "";
function mixLine(w) {
  const n = (f) => (w.problems || []).filter((p) => p.focus === f).length;
  const parts = [n("missed") && n("missed") + " redo your misses", n("kept") && n("kept") + " keep it fresh", n("new") && n("new") + " new"].filter(Boolean);
  return n("missed") || n("kept") ? `<p class="mix-line">This sheet: ${parts.join(" · ")}</p>` : "";
}

function renderKit(k) {
  kitBody.hidden = false;
  queueMicrotask(() => { const cur = document.querySelector(".subtabs [aria-pressed=true]")?.dataset.sub; if (cur) showSection(cur); });
  document.getElementById("quiz-none").hidden = document.getElementById("quiz-empty").hidden = true;
  document.getElementById("quiz-links").hidden = false;
  window.currentKit = k;
  fetch("/api/progress?quiz=" + encodeURIComponent(k.quiz)).then((r) => r.json()).then((p) => { progress = p; drawPlan(); drawReady(); markSheet(); });
  const r = k.review || {};
  const pane = (n) => document.querySelector(`[data-pane="${n}"]`);
  window.drawPlan = () => {
    const steps = planSteps(window.nextQuiz?.due || Date.now());
    const days = [...new Set(steps.map((s) => s.day))];
    const label = (d) => { const t = new Date(Date.now() + d * 86400000); return d === 0 ? "Today" : t.toLocaleDateString(undefined, { weekday: "long" }); };
    pane("plan").innerHTML = days.map((d) => `<section class="card"><h3>${label(d)}</h3>
      ${steps.filter((s) => s.day === d).map((s) => `<label class="check plan-step"><input type="checkbox" data-step="${s.id}" ${Ready.doneSteps(progress, window.currentKit).has(s.id) ? "checked" : ""}>
        <span>${esc(s.label)}</span> <button type="button" class="link" data-open="${s.tab}">open</button></label>`).join("")}</section>`).join("")
      + (Object.keys(progress.marks || {}).some((k2) => progress.marks[k2] === "wrong") ? `<section class="card warn-card"><h3>Your weak spots</h3><ul>${
        Object.entries(progress.marks).filter(([, v]) => v === "wrong").map(([key]) => `<li>${esc(key)}</li>`).join("")}</ul></section>` : "");
  };
  pane("plan").onclick = (e) => {
    const open = e.target.dataset?.open;
    if (open) { open === "test" ? document.querySelector('[data-tab="practice"]').click() : document.querySelector(`[data-sub="${open}"]`).click(); }
  };
  pane("plan").onchange = (e) => {
    const id = e.target.dataset?.step; if (!id) return;
    saveProgress({ plan: { ...(progress.plan || {}), [id]: e.target.checked } });
  };
  pane("review").innerHTML = `
    <p class="muted small">Built ${new Date(k.builtAt).toLocaleString()} from: ${k.sources.length ? esc(k.sources.join(", ")) : "general knowledge (no slides found)"}</p>
    ${r.bigIdea ? `<div class="card big-idea"><strong>Big idea:</strong> ${esc(r.bigIdea)}</div>` : ""}
    ${(r.sections || []).map((s) => `<section class="card"><h3>${esc(s.heading)}</h3><ul>${(s.points || []).map((p) => `<li>${esc(p)}</li>`).join("")}</ul>
      ${s.example ? `<div class="example"><strong>Example:</strong> ${esc(s.example.problem)}<ol>${(s.example.steps || []).map((x) => `<li>${esc(x)}</li>`).join("")}</ol><p><strong>Answer:</strong> ${esc(s.example.answer)}</p></div>` : ""}</section>`).join("")}
    ${(r.steps || []).length ? `<section class="card"><h3>Step-by-step recipes</h3>${r.steps.map((s) => `<h4>${esc(s.name)}</h4><ol>${s.steps.map((x) => `<li>${esc(x)}</li>`).join("")}</ol>`).join("")}</section>` : ""}
    ${(r.traps || []).length ? `<section class="card warn-card"><h3>Traps to watch for</h3><ul>${r.traps.map((t) => `<li>${esc(t)}</li>`).join("")}</ul></section>` : ""}`;
  pane("symbols").innerHTML = `
    <section class="card"><h3>Symbols</h3><table><thead><tr><th>Symbol</th><th>Say it</th><th>Means</th></tr></thead><tbody>
      ${(r.symbols || []).map((s) => `<tr><td class="sym">${esc(s.symbol)}</td><td>${esc(s.say)}</td><td>${esc(s.means)}</td></tr>`).join("")}</tbody></table></section>
    <section class="card"><h3>Formulas to memorize</h3><table><thead><tr><th>Name</th><th>Formula</th><th>Use it when</th></tr></thead><tbody>
      ${(r.formulas || []).map((f) => `<tr><td>${esc(f.name)}</td><td class="sym">${esc(f.formula)}</td><td>${esc(f.use)}</td></tr>`).join("")}</tbody></table></section>`;
  // flashcards
  let i = 0, flipped = false, order = k.cards.map((_, n) => n);
  const known = new Set(progress.known || []);
  setTimeout(() => { (progress.known || []).forEach((n) => known.add(n)); }, 400);
  const draw = () => {
    if (!k.cards.length) { pane("cards").innerHTML = "<p class='muted'>No flashcards.</p>"; return; }
    const c = k.cards[order[i]];
    pane("cards").innerHTML = `
      <p class="muted small">Card ${i + 1} of ${order.length} · ${known.size} marked known · Space flips, arrows move</p>
      <button type="button" class="flashcard ${flipped ? "flipped" : ""}" id="fc" aria-label="Flashcard, ${flipped ? "showing answer" : "showing question"}. Click to flip.">
        <span class="kind">${esc(c.kind)}</span><span class="face">${esc(flipped ? c.back : c.front)}</span></button>
      <p class="fc-controls"><button type="button" class="secondary" data-fc="prev">← Back</button>
        <button type="button" class="secondary" data-fc="known">${known.has(order[i]) ? "✓ Known" : "I know this"}</button>
        <button type="button" class="secondary" data-fc="shuffle">Shuffle</button>
        <button type="button" class="secondary" data-fc="unknown">Only cards I don't know</button>
        <button type="button" class="primary" data-fc="next">Next →</button></p>`;
  };
  const act = (a) => {
    if (a === "flip") flipped = !flipped;
    if (a === "next") { i = (i + 1) % order.length; flipped = false; }
    if (a === "prev") { i = (i - 1 + order.length) % order.length; flipped = false; }
    if (a === "known") { known.has(order[i]) ? known.delete(order[i]) : known.add(order[i]); saveProgress({ known: [...known] }); }
    if (a === "shuffle") { order.sort(() => Math.random() - 0.5); i = 0; flipped = false; }
    if (a === "unknown") { const rest = k.cards.map((_, n) => n).filter((n) => !known.has(n)); if (rest.length) { order = rest; i = 0; flipped = false; } }
    draw();
  };
  pane("cards").onclick = (e) => { const b = e.target.closest("button"); if (!b) return; act(b.id === "fc" ? "flip" : b.dataset.fc); };
  document.onkeydown = (e) => {
    if (pane("cards").hidden || pane("cards").closest(".kit-page").hidden || /input|textarea|select/i.test(e.target.tagName)) return;
    if (e.key === " ") { e.preventDefault(); act("flip"); } if (e.key === "ArrowRight") act("next"); if (e.key === "ArrowLeft") act("prev");
  };
  draw();
  // worksheet redo
  const w = k.worksheet;
  pane("sheet").innerHTML = w ? `
    <p class="no-print"><button type="button" class="primary" id="ws-new">Make a new worksheet</button>
      <button type="button" class="secondary" id="ws-sol" aria-pressed="false">Show solutions</button>
      <button type="button" class="secondary" id="ws-print">Print</button></p>
    <p id="ws-new-status" class="muted small no-print" aria-live="polite">Mark each part ✓ or ✗ under Show solutions. The next worksheet focuses on your ✗s and keeps a couple of ✓s fresh.</p>
    ${mixLine(w)}
    ${w.messy?.length ? `<p class="warn small">Heads up: some numbers here still need a calculator (${esc(w.messy.slice(0, 3).join("; "))}). Click Rebuild for a cleaner set.</p>` : `<p class="muted small">✓ Every number works by hand.</p>`}
    <article class="paper" id="ws-paper"><header class="paper-head"><span>${esc(COURSE_LABELS.paperLabel || "Practice")}</span><span>${esc(String(k.quiz).replace(/\s*\(.*\)$/, ""))}</span></header>
      <h2>${esc(String(k.quiz).replace(/\s*\(.*\)$/, ""))} practice worksheet</h2>
      <ol class="questions">${(w.problems || []).map((p) => `<li>${focusTag(p.focus)}<p>${esc(p.text)}</p>
        ${(p.parts || []).map((x) => `<div class="part"><p><strong>${esc(x.label)}</strong> ${esc(x.text)}</p><div class="work-space"></div>
          <div class="answer"><strong>Answer:</strong> ${esc(x.answer)}<br><span class="sol">${esc(x.solution)}</span>${wsFlag(x.flag)}
          ${markBtns("Problem " + p.number + " " + x.label)}</div></div>`).join("")}
        ${!(p.parts || []).length ? `<div class="work-space"></div><div class="answer"><strong>Answer:</strong> ${esc(p.answer)}<br><span class="sol">${esc(p.solution)}</span>${wsFlag(p.flag)}${markBtns("Problem " + p.number)}</div>` : ""}</li>`).join("")}</ol></article>`
    : "<p class='muted'>Tick at least one worksheet above and rebuild to get a fresh worksheet.</p>";
  pane("sheet").onclick = (e) => {
    const b = e.target.closest("[data-mark]"); if (!b) return;
    saveProgress({ marks: { ...(progress.marks || {}), [b.dataset.key]: b.dataset.mark } }).then(markSheet);
    markSheet(); drawPlan();
  };
  const wsBtn = document.getElementById("ws-sol");
  if (wsBtn) wsBtn.onclick = () => { const on = wsBtn.getAttribute("aria-pressed") !== "true";
    wsBtn.setAttribute("aria-pressed", String(on)); wsBtn.textContent = on ? "Hide solutions" : "Show solutions";
    document.getElementById("ws-paper").classList.toggle("show-answers", on); };
  const wsPrint = document.getElementById("ws-print");
  if (wsPrint) wsPrint.onclick = () => printPaper(document.getElementById("ws-paper"), String(k.quiz).replace(/\s*\(.*\)$/, "") + " practice worksheet");
  const wsNew = document.getElementById("ws-new");
  if (wsNew) wsNew.onclick = async () => {
    const st = document.getElementById("ws-new-status");
    wsNew.disabled = true; st.textContent = "Writing a new worksheet from your ✓ and ✗ marks… (about 40 seconds)";
    try {
      const r = await fetch("/api/kit", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...window.kitInfo, only: "worksheet", worksheets: [...document.querySelectorAll("input[name=ws]:checked")].map((c) => c.value) }) });
      const kit = await r.json(); if (!r.ok) throw new Error(kit.error);
      renderKit(kit); document.querySelector('[data-sub="sheet"]').click();
    } catch (x) { st.textContent = x.message || "Couldn't make a new worksheet."; wsNew.disabled = false; }
  };
}


// ── Math at a glance (from Today planner) ──
function drawMath() {
  const p = window.planner, box = document.getElementById("math-overview");
  if (!p) return;
  const g = p.grades, info = p.info || {};
  const cats = (g?.categories || []).filter((c) => c.items?.length);
  box.hidden = false;
  box.innerHTML = `<h3>Math at a glance</h3>
    ${cats.length ? `<table><thead><tr><th>Category</th><th>Weight</th><th>Your grade</th></tr></thead><tbody>
      ${cats.map((c) => `<tr><td>${esc(c.name)}</td><td>${Math.round(c.weight * 100)}%</td><td>${c.pct ?? "?"}%${/exam/i.test(c.name) && c.pct === 0 ? " <span class='muted small'>(0 usually means not released yet)</span>" : ""}</td></tr>`).join("")}
    </tbody></table>` : ""}
    ${p.homework?.length ? `<h4>Homework due</h4><ul>${p.homework.map((h) => `<li><strong>${esc(h.title)}</strong> · ${fmtDay(h.due)}</li>`).join("")}</ul>` : ""}
    <h4>Coming up</h4><ul>${p.quizzes.slice(1, 4).map((q) => `<li>${esc(q.title)} · ${fmtDay(q.due)}</li>`).join("")}</ul>
    <details><summary>Class info</summary><ul>
      ${info.instructor ? `<li>Instructor: ${esc(info.instructor)}</li>` : ""}
      ${info.meets ? `<li>${esc(info.meets.day)} ${esc(info.meets.start)} to ${esc(info.meets.end)}, ${esc(info.meets.room)}</li>` : ""}
      ${info.attendance ? `<li>${esc(info.attendance)}</li>` : ""}
    </ul></details>`;
}


function markBtns(key) {
  return `<span class="marks no-print" role="group" aria-label="How did you do?">
    <button type="button" class="mark" data-key="${esc(key)}" data-mark="right" aria-pressed="false">✓ got it</button>
    <button type="button" class="mark" data-key="${esc(key)}" data-mark="wrong" aria-pressed="false">✗ missed</button></span>`;
}
function markSheet() {
  document.querySelectorAll("button.mark").forEach((b) => b.setAttribute("aria-pressed", String((progress.marks || {})[b.dataset.key] === b.dataset.mark)));
}

// Practice test timer (recitation quizzes are short; practice under time)
(function addTimer() {
  const bar = document.querySelector("#practice-out .no-print"); if (!bar) return;
  const btn = document.createElement("button"); btn.type = "button"; btn.className = "secondary"; btn.textContent = "Start 20-min timer";
  const out = document.createElement("span"); out.className = "timer"; out.setAttribute("aria-live", "off");
  bar.append(" ", btn, " ", out);
  let t = null;
  btn.onclick = () => {
    if (t) { clearInterval(t); t = null; out.textContent = ""; btn.textContent = "Start 20-min timer"; return; }
    const end = Date.now() + 20 * 60000; btn.textContent = "Stop timer";
    t = setInterval(() => {
      const left = Math.max(0, end - Date.now()), m = Math.floor(left / 60000), sec = Math.floor(left / 1000) % 60;
      out.textContent = m + ":" + String(sec).padStart(2, "0");
      if (!left) { clearInterval(t); t = null; out.textContent = "Time! Pens down."; btn.textContent = "Start 20-min timer"; }
    }, 250);
  };
})();

// ── Exam mode ──
let exam = null;
const examPlanStore = () => { try { return JSON.parse(localStorage.getItem("exam-done") || "{}"); } catch { return {}; } };
const saveExamDone = (d) => { try { localStorage.setItem("exam-done", JSON.stringify(d)); } catch {} };

async function loadExam() {
  const head = document.getElementById("exam-head");
  try {
    const r = await fetch("/api/exam"); exam = await r.json();
    if (!r.ok) throw new Error(exam.error);
    if (!exam) { head.innerHTML = "<p>No exam coming up.</p>"; return; }
    const d = daysLeft(exam.due);
    const known = exam.lessons.filter((l) => l.skill !== null);
    const avg = known.length ? Math.round(known.reduce((a, l) => a + l.skill, 0) / known.length) : null;
    head.innerHTML = `<h3>${esc(exam.title)} · ${fmtDay(exam.due)} <span class="pill">in ${d} days</span></h3>
      <p>Covers ${exam.lessons.map((l) => `Lesson ${l.n} (${esc(l.name)})`).join(", ")}.</p>
      <p class="muted small">${avg === null ? "Take a skill check on each lesson so the schedule knows where to focus." : `Average skill so far: <strong>${avg}%</strong> across ${known.length} of ${exam.lessons.length} lessons.`}</p>`;
    drawSkills(); drawExamPlan();
  } catch (x) { head.innerHTML = `<p class="error">${esc(x.message || "Couldn't load the exam.")}</p>`; }
}

function skillBand(s) {
  if (s === null) return ["unknown", "Not measured"];
  if (s >= 85) return ["strong", "Strong"];
  if (s >= 65) return ["ok", "Getting there"];
  return ["weak", "Needs work"];
}

function drawSkills() {
  document.getElementById("skill-list").innerHTML = exam.lessons.map((l) => {
    const [cls, label] = skillBand(l.skill);
    return `<div class="skill-row">
      <div class="skill-name"><strong>Lesson ${l.n}</strong> <span>${esc(l.name)}</span>
        <span class="muted small">${l.slides.length ? esc(l.why.join(" · ")) : "slides not in Downloads yet"}</span></div>
      <div class="skill-meter ${cls}" role="meter" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${l.skill ?? 0}" aria-label="Lesson ${l.n} skill">
        <span style="width:${l.skill ?? 0}%"></span></div>
      <div class="skill-val"><span class="tag ${cls}">${l.skill === null ? label : l.skill + "%"}</span></div>
      <button type="button" class="secondary small" data-check="${l.n}" ${l.slides.length ? "" : "disabled title=\"Download this lesson's slides first\""}>Skill check</button>
    </div>`;
  }).join("");
}

// Spread study time over the days left: weakest first, mixed review, then full practice exams.
function buildExamPlan() {
  const mins = Number(document.getElementById("exam-minutes").value);
  const days = Math.max(daysLeft(exam.due) - 1, 1);
  const need = exam.lessons.map((l) => ({ ...l, need: l.slides.length ? (100 - (l.skill ?? 40)) / 100 : 0.7, ready: l.slides.length > 0 }));
  const finalDays = Math.min(2, Math.max(days - 1, 0));
  const learnDays = days - finalDays;
  const sessions = [];
  // each lesson gets sessions proportional to need, at least one
  const totalNeed = need.reduce((a, l) => a + Math.max(l.need, 0.15), 0);
  need.forEach((l) => {
    const count = Math.max(1, Math.round(learnDays * Math.max(l.need, 0.15) / totalNeed));
    for (let i = 0; i < count; i++) sessions.push({ l, round: i });
  });
  // weakest and available first; untaught lessons go later
  sessions.sort((a, b) => (b.l.ready - a.l.ready) || (a.round - b.round) || (b.l.need - a.l.need));
  const plan = Array.from({ length: days }, (_, i) => ({ day: i, items: [] }));
  sessions.forEach((s, i) => {
    const day = Math.min(Math.floor(i * learnDays / sessions.length), learnDays - 1);
    const l = s.l;
    const what = !l.ready ? "Learn from the slides once posted, then skill check"
      : s.round === 0 ? (l.skill === null ? "Skill check, then Review + flashcards" : l.skill < 65 ? "Review + worked examples, then worksheet" : "Worksheet, redo anything ✗")
      : "Fresh worksheet (rebuild), focus on ✗ parts, skill check again";
    plan[day].items.push({ id: `L${l.n}-${s.round}`, text: `Lesson ${l.n} · ${l.name}: ${what}`, lesson: l.n, mins: Math.round(mins / Math.max(1, Math.ceil(sessions.length / learnDays))) });
  });
  for (let f = 0; f < finalDays; f++) {
    plan[learnDays + f].items.push({ id: `final-${f}`, text: f === finalDays - 1 ? "Night before: flashcards for every lesson, formula sheet from memory" : "Full practice exam, timed, no notes, no calculator. Then redo every miss.", mins });
  }
  return plan;
}

function drawExamPlan() {
  const done = examPlanStore();
  const plan = buildExamPlan();
  document.getElementById("exam-plan").innerHTML = plan.map((d) => {
    const date = new Date(Date.now() + d.day * 86400000);
    const label = d.day === 0 ? "Today" : d.day === 1 ? "Tomorrow" : date.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
    if (!d.items.length) return "";
    return `<div class="plan-day"><h4>${label}</h4>${d.items.map((it) => `<label class="check plan-step">
      <input type="checkbox" data-exam-step="${it.id}" ${done[it.id] ? "checked" : ""}><span>${esc(it.text)} <span class="muted small">~${it.mins} min</span></span></label>`).join("")}</div>`;
  }).join("");
}

document.getElementById("exam-plan").addEventListener("change", (e) => {
  const id = e.target.dataset?.examStep; if (!id) return;
  const d = examPlanStore(); d[id] = e.target.checked; saveExamDone(d);
});
document.getElementById("exam-minutes").addEventListener("change", () => exam && drawExamPlan());

// Skill check: 6 questions from the lesson's slides, scored on the spot.
document.getElementById("skill-list").addEventListener("click", async (e) => {
  const n = Number(e.target.closest("[data-check]")?.dataset.check); if (!n) return;
  const l = exam.lessons.find((x) => x.n === n), box = document.getElementById("skill-check");
  box.hidden = false; box.className = "card";
  box.innerHTML = `<p class="muted">Writing a skill check for Lesson ${n} from your slides… (about 20 seconds)</p>`;
  box.scrollIntoView({ behavior: "smooth", block: "start" });
  try {
    const r = await fetch("/api/skillcheck", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ lesson: n, name: l.name }) });
    const d = await r.json(); if (!r.ok) throw new Error(d.error);
    runCheck(l, d.questions, box);
  } catch (x) { box.innerHTML = `<p class="error">${esc(x.message)}</p>`; }
});

function runCheck(l, qs, box) {
  // Skipped questions count neither way: the score is right out of the ones she answered.
  let i = 0, right = 0, skipped = 0;
  const step = () => {
    if (i >= qs.length) {
      const answered = qs.length - skipped;
      box.innerHTML = `<h3>Lesson ${l.n} skill check: ${right} / ${answered}${skipped ? ` <span class="muted small">· ${skipped} skipped</span>` : ""}</h3>
        <p class="muted">${answered ? "Saved. Your skill and schedule updated." : "You skipped them all, so nothing was saved."}</p>
        <p><button type="button" class="secondary" id="close-check">Close</button></p>`;
      if (answered) fetch("/api/skill", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ lesson: l.n, score: right, of: answered }) })
        .then(loadExam);
      document.getElementById("close-check").onclick = () => { box.hidden = true; };
      return;
    }
    const q = qs[i];
    box.innerHTML = `<div class="row-between"><h3>Lesson ${l.n} skill check</h3><span class="muted small">${i + 1} of ${qs.length} · ${right} right${skipped ? " · " + skipped + " skipped" : ""}</span></div>
      <p class="stem">${esc(q.q)}</p><div class="opts">${q.o.map((o, j) => `<button type="button" class="opt" data-o="${j}"><b>${"ABCD"[j]}</b> ${esc(o)}</button>`).join("")}</div>
      <p class="skip-row"><button type="button" class="link" id="skip-q">Skip this one →</button></p>
      <div class="why" hidden></div>`;
    document.getElementById("skip-q").onclick = () => { skipped++; i++; step(); };
    box.querySelector(".opts").onclick = (e) => {
      const b = e.target.closest("[data-o]"); if (!b) return;
      const pick = Number(b.dataset.o), ok = pick === q.a; if (ok) right++;
      box.querySelectorAll(".opt").forEach((x, j) => { x.disabled = true; if (j === q.a) x.classList.add("right"); else if (j === pick) x.classList.add("wrong"); });
      box.querySelector(".skip-row").hidden = true;
      const why = box.querySelector(".why"); why.hidden = false;
      why.innerHTML = `<p><strong>${ok ? "Right." : "Not quite. Answer: " + "ABCD"[q.a]}</strong></p><ol>${(q.w || []).map((w) => `<li>${esc(w)}</li>`).join("")}</ol>
        <p><button type="button" class="primary" id="next-q">${i + 1 < qs.length ? "Next" : "See score"}</button></p>`;
      document.getElementById("next-q").onclick = () => { i++; step(); };
    };
  };
  step();
}

// Exam study kit: same kit, built across every exam lesson.
document.getElementById("exam-kit-btn").addEventListener("click", async (e) => {
  if (!exam) return;
  const btn = e.currentTarget, st = document.getElementById("exam-kit-status");
  btn.disabled = true; st.textContent = "Building from every exam lesson's slides… (about a minute)";
  window.kitInfo = { quiz: exam.title, lessons: exam.lessons.map((l) => l.n), topics: exam.lessons.map((l) => l.name).join(", ") };
  try {
    const sheets = [...document.querySelectorAll("input[name=ws]:checked")].map((c) => c.value);
    const r = await fetch("/api/kit", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...window.kitInfo, worksheets: sheets }) });
    const kit = await r.json(); if (!r.ok) throw new Error(kit.error);
    showKitMode(exam.title); renderKit(kit); openTab("kit"); showKitPage("quiz/plan"); st.textContent = "";
  } catch (x) { st.textContent = x.message || "Couldn't build it."; }
  finally { btn.disabled = false; }
});

function showKitMode(title) {
  const note = document.getElementById("kit-mode");
  note.hidden = false;
  note.innerHTML = `Showing the <strong>${esc(title)}</strong> kit. <button type="button" class="link" id="back-quiz">Back to the next quiz</button>`;
  document.getElementById("back-quiz").onclick = () => { note.hidden = true; initKit(); };
}

loadExam();
document.querySelector('[data-tab="exam"]').addEventListener("click", () => exam && loadExam());

// ── Study Kit pages ──
// One page at a time, each with its own hash so Back works: #kit, #kit/quiz/<section>, #kit/lesson, #kit/settings, #kit/math.
const SECTIONS = ["plan", "review", "symbols", "cards", "sheet", "test"];
const SECTION_NAME = { plan: "Plan", review: "Review", symbols: "Symbols & formulas", cards: "Flashcards", sheet: "Worksheet", test: "Practice test" };
const store = {   // per-browser conveniences only (last page, lesson step); the app works without them
  get: (k) => { try { return localStorage.getItem(k); } catch { return null; } },
  set: (k, v) => { try { localStorage.setItem(k, String(v)); } catch {} }
};
const quizName = () => String(window.kitInfo?.quiz || "Quiz").replace(/\s*\(.*\)$/, "");

function showKitPage(route = "", push = true) {
  const [page, sub] = String(route).split("/");
  const name = ["quiz", "lesson", "settings", "math", "saved"].includes(page) ? page : "home";
  const section = SECTIONS.includes(sub) ? sub : "plan";
  document.querySelectorAll(".kit-page").forEach((p) => (p.hidden = p.dataset.page !== name));
  if (name === "quiz") showSection(section);
  if (name === "lesson") openLessonPage();
  if (name === "home") { drawResume(); drawLessonDoor(); }
  if (name === "saved") drawSaved();
  const hash = "#kit" + (name === "home" ? "" : "/" + name + (name === "quiz" ? "/" + section : ""));
  if (location.hash !== hash) history[push ? "pushState" : "replaceState"](null, "", hash);
  if (name === "quiz" || name === "lesson") store.set("qp.lastPage", hash.slice(5));
  window.scrollTo(0, 0);
}
function showSection(sub) {
  document.querySelectorAll(".subtabs button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.sub === sub)));
  document.querySelectorAll("[data-pane]").forEach((p) => (p.hidden = p.dataset.pane !== sub));
  document.getElementById("quiz-title").textContent = quizName() + " · " + SECTION_NAME[sub];
  const next = SECTIONS[SECTIONS.indexOf(sub) + 1], btn = document.getElementById("quiz-next");
  btn.textContent = next ? "Next: " + SECTION_NAME[next] + " →" : "Done: back to Study Kit";
  btn.onclick = () => showKitPage(next ? "quiz/" + next : "");
  drawGuide();
}
function drawResume() {
  const last = store.get("qp.lastPage"), b = document.getElementById("resume");
  const [page, sub] = String(last || "").split("/");
  const label = page === "lesson" ? "New lesson" + (lesson ? " · Lesson " + lesson.number : "") : SECTION_NAME[sub] ? quizName() + " · " + SECTION_NAME[sub] : "";
  b.hidden = !label;
  if (!label) return;
  b.innerHTML = `<span>▶ Pick up where you left off</span><strong>${esc(label)}</strong>`;
  b.onclick = () => showKitPage(last);
}
document.getElementById("kit").addEventListener("click", (e) => {
  const go = e.target.closest("[data-go]")?.dataset.go;
  if (go) showKitPage(go === "home" ? "" : go);
});
document.querySelector('[data-tab="kit"]').addEventListener("click", () => showKitPage(""));
addEventListener("popstate", () => {
  const [tab, ...rest] = location.hash.slice(1).split("/");
  if (tab && [...tabs].some((t) => t.dataset.tab === tab)) openTab(tab);
  if (!tab || tab === "kit") showKitPage(rest.join("/"), false);
});

// ── New lesson: a recap of last week, this week's slides in small visual steps, then a cheat sheet ──
let lessonList = null, lesson = null, lessonStep = 0;
const lessonKey = (n) => "qp.lesson." + n;
const loadLessonList = async () => (lessonList ||= await (await fetch("/api/lessons")).json());
const lessonSteps = (L) => [...(L.recap ? [{ kind: "recap", name: "Recap of Lesson " + L.recap.lesson }] : []),
  ...L.chunks.map((c, i) => ({ kind: "chunk", i, name: c.title })), { kind: "cheat", name: "Cheat sheet" }];

async function drawLessonDoor() {
  const box = document.getElementById("lesson-door");
  try {
    const list = await loadLessonList(), l = list[0];
    if (!l) { box.innerHTML = "<p class='muted'>No lesson slides in Downloads yet.</p>"; return; }
    const prev = list.find((x) => x.number < l.number);
    const saved = l.built ? await (await fetch("/api/lesson?n=" + l.number)).json() : null;
    const total = saved ? lessonSteps(saved).length : 0, at = Math.min(Number(store.get(lessonKey(l.number)) || 0), Math.max(total - 1, 0));
    box.innerHTML = `<h3>Lesson ${l.number} · ${esc(l.title)}</h3>
      ${prev ? `<p class="muted small">Starts with a quick recap of Lesson ${prev.number} · ${esc(prev.title)}</p>` : ""}
      ${saved ? `<p class="dots" role="img" aria-label="Step ${at + 1} of ${total}">${Array.from({ length: total }, (_, i) => `<span class="${i < at ? "done" : i === at ? "now" : ""}"></span>`).join("")}</p>` : ""}
      <p><button type="button" class="primary" data-go="lesson">${saved ? (at ? "Keep going →" : "Start →") : "Build this lesson"}</button></p>`;
  } catch { box.innerHTML = "<p class='error'>Couldn't look for lessons.</p>"; }
}

async function openLessonPage(n) {
  const list = await loadLessonList(), pick = document.getElementById("lesson-pick");
  const want = n || lesson?.number || list[0]?.number;
  pick.innerHTML = list.map((l) => `<option value="${l.number}" ${l.number === want ? "selected" : ""}>${l.number} · ${esc(l.title)}</option>`).join("");
  if (!want) { document.getElementById("lesson-body").innerHTML = "<p class='muted'>No lesson slides in Downloads yet.</p>"; return; }
  if (lesson?.number === want) return drawLessonStep();
  const saved = await (await fetch("/api/lesson?n=" + want)).json();
  if (saved) {
    lesson = saved;
    lessonStep = Math.min(Number(store.get(lessonKey(want)) || 0), lessonSteps(saved).length - 1);
    return drawLessonStep();
  }
  lesson = null;
  document.getElementById("lesson-body").innerHTML = `<div class="card lesson-build"><h3>Lesson ${want} isn't built yet</h3>
    <p>This reads the slides and turns them into a short, visual lesson${list.some((x) => x.number < want) ? ", with a recap of last week first" : ""}. It takes about a minute.</p>
    <p><button type="button" class="primary" id="lesson-build">Build Lesson ${want}</button> <span class="muted small" id="lesson-status" aria-live="polite"></span></p></div>`;
  document.getElementById("lesson-build").onclick = () => buildLesson(want);
}
document.getElementById("lesson-pick").onchange = (e) => openLessonPage(Number(e.target.value));

async function buildLesson(n) {
  const btn = document.getElementById("lesson-build") || document.getElementById("lesson-rebuild");
  const st = document.getElementById("lesson-status");
  if (btn) btn.disabled = true;
  if (st) st.textContent = "Reading the slides and drawing the lesson… (about a minute)";
  try {
    const r = await fetch("/api/lesson", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ number: n }) });
    const d = await r.json(); if (!r.ok) throw new Error(d.error);
    lesson = d; lessonStep = 0; store.set(lessonKey(n), 0); lessonList = null;
    drawLessonStep();
  } catch (x) {
    if (st) st.textContent = (x.message || "Couldn't build it.") + " Click Build again.";
    if (btn) btn.disabled = false;
  }
}

const recapCard = (r) => `<article class="card lesson-card recap">
  <p class="kicker">Last week · Lesson ${r.lesson}${r.title ? " · " + esc(r.title) : ""}</p>
  <p class="big-rule">${esc(r.rule)}</p>
  ${Diagrams.diagram(r.diagram)}
  ${r.recall.length ? `<h4>Quick recall: say it, then peek</h4>${r.recall.map((x) => `<details class="recall"><summary>${esc(x.q)}</summary><p>${esc(x.a)}</p></details>`).join("")}` : ""}
</article>`;

const checkBlock = (q) => `<section class="qcheck"><h4>Quick check</h4><p class="stem">${esc(q.q)}</p>
  <div class="opts">${q.choices.map((o, j) => `<button type="button" class="opt" data-pick="${j}"><b>${"ABCD"[j]}</b> ${esc(o)}</button>`).join("")}</div>
  <div class="why" hidden></div></section>`;

const chunkCard = (c, i, n) => `<article class="card lesson-card">
  <p class="kicker">This week · ${i + 1} of ${n}${c.page ? ` <span class="page-chip">slides p.${c.page}</span>` : ""}</p>
  <h3>${esc(c.title)}</h3>
  <p class="idea">${esc(c.idea)}</p>
  ${Diagrams.diagram(c.diagram)}
  ${c.example ? `<section class="example"><h4>Worked example</h4><p class="ex-q">${esc(c.example.problem)}</p>
    <ol class="ex-steps">${c.example.steps.map((s) => `<li>${esc(s)}</li>`).join("")}</ol>
    <p class="ex-answer">${esc(c.example.answer)}</p>${c.computed ? `<p class="muted small">✓ The app worked these numbers out itself.</p>` : ""}</section>` : ""}
  ${c.hook ? `<p class="hook"><span aria-hidden="true">🧠</span> ${esc(c.hook)}</p>` : ""}
  ${c.check ? checkBlock(c.check) : ""}
  ${c.flag ? `<p class="ws-flag"><strong>Double-check this one.</strong> ${esc(c.flag)}</p>` : ""}
</article>`;

const cheatSheet = (L) => `<article class="paper cheat" id="cheat-paper">
  <header class="paper-head"><span>Cheat sheet</span><span>Lesson ${L.number} · ${esc(L.title)}</span></header>
  <h2>${esc(L.title)}</h2>
  <div class="cheat-grid">${L.chunks.map((c) => `<section><h4>${esc(c.title)}</h4>${Diagrams.diagram(c.diagram)}<p>${esc(c.idea)}</p>${c.hook ? `<p class="hook">🧠 ${esc(c.hook)}</p>` : ""}</section>`).join("")}</div>
</article>
<p class="no-print"><button type="button" class="secondary" id="cheat-print">Print cheat sheet</button></p>`;

function drawLessonStep() {
  const steps = lessonSteps(lesson), s = steps[lessonStep], body = document.getElementById("lesson-body");
  store.set(lessonKey(lesson.number), lessonStep);
  const strip = `<nav class="step-strip" aria-label="Lesson steps">${steps.map((x, i) =>
    `<button type="button" data-step="${i}" class="${i < lessonStep ? "done" : ""}" ${i === lessonStep ? 'aria-current="step"' : ""} title="${esc(x.name)}" aria-label="${esc(i + 1 + ". " + x.name)}"></button>`).join("")}</nav>`;
  const card = s.kind === "recap" ? recapCard(lesson.recap) : s.kind === "chunk" ? chunkCard(lesson.chunks[s.i], s.i, lesson.chunks.length) : cheatSheet(lesson);
  const last = lessonStep === steps.length - 1;
  body.innerHTML = `${strip}<div class="lesson-step">${card}</div>
    <p class="step-nav no-print"><button type="button" class="secondary" id="step-back" ${lessonStep ? "" : "disabled"}>← Back</button>
      <span class="muted small">${lessonStep + 1} of ${steps.length}</span>
      ${last ? `<button type="button" class="primary" data-go="home">Done</button>` : `<button type="button" class="primary" id="step-next">Next: ${esc(steps[lessonStep + 1].name)} →</button>`}</p>
    <p class="muted small lesson-foot no-print">Built ${new Date(lesson.builtAt).toLocaleDateString()} from your slides. <button type="button" class="link" id="lesson-rebuild">Rebuild</button> <span id="lesson-status" aria-live="polite"></span></p>`;
  const go = (i) => { lessonStep = Math.max(0, Math.min(steps.length - 1, i)); drawLessonStep(); window.scrollTo(0, 0); };
  body.querySelector(".step-strip").onclick = (e) => { const b = e.target.closest("[data-step]"); if (b) go(Number(b.dataset.step)); };
  document.getElementById("step-back").onclick = () => go(lessonStep - 1);
  const next = document.getElementById("step-next"); if (next) next.onclick = () => go(lessonStep + 1);
  document.getElementById("lesson-rebuild").onclick = () => buildLesson(lesson.number);
  const pr = document.getElementById("cheat-print");
  if (pr) pr.onclick = () => printPaper(document.getElementById("cheat-paper"), "Lesson " + lesson.number + " cheat sheet");
  const chk = body.querySelector(".qcheck");
  if (chk) chk.onclick = (e) => {
    const b = e.target.closest("[data-pick]"); if (!b) return;
    const q = lesson.chunks[s.i].check, pick = Number(b.dataset.pick), ok = pick === q.answer;
    chk.querySelectorAll(".opt").forEach((x, j) => { x.disabled = true; if (j === q.answer) x.classList.add("right"); else if (j === pick) x.classList.add("wrong"); });
    const why = chk.querySelector(".why"); why.hidden = false;
    why.innerHTML = `<p><strong>${ok ? "Right." : "Not quite: it's " + "ABCD"[q.answer] + "."}</strong> ${esc(q.why)}</p>`;
  };
}
document.addEventListener("keydown", (e) => {
  if (!lesson || document.querySelector('[data-page="lesson"]').hidden || /input|textarea|select/i.test(e.target.tagName)) return;
  if (e.key === "ArrowRight") document.getElementById("step-next")?.click();
  if (e.key === "ArrowLeft") document.getElementById("step-back")?.click();
});

// first page from the address: "#kit/lesson" opens the lesson, a bare "#kit" (or nothing) the home page
{ const [tab, ...rest] = location.hash.slice(1).split("/"); if (!tab || tab === "kit") showKitPage(rest.join("/"), false); }

// ── Ask chatbot (bottom-right): questions about whatever is on screen, answered from the slides ──
const askOpen = document.getElementById("ask-open"), askPanel = document.getElementById("ask-panel");
const askLog = document.getElementById("ask-log"), askInput = document.getElementById("ask-input"), askHistory = [];

// What she is looking at: the visible page's text, a short label for it, and which lessons' slides back it up.
function screenContext() {
  const tab = [...tabs].find((t) => t.getAttribute("aria-selected") === "true")?.dataset.tab || "kit";
  let el = document.getElementById(tab), where = document.querySelector(`[data-tab="${tab}"]`).textContent, lessons = window.kitInfo?.lessons || [];
  if (tab === "kit") {
    const page = document.querySelector(".kit-page:not([hidden])"), name = page?.dataset.page;
    el = page || el; where = "Study Kit home";
    if (name === "quiz") { where = document.getElementById("quiz-title").textContent; el = page.querySelector("[data-pane]:not([hidden])") || page; }
    if (name === "lesson" && lesson) {
      where = `Lesson ${lesson.number} · ${lessonSteps(lesson)[lessonStep].name}`;
      lessons = [lesson.number, lesson.recap?.lesson].filter(Boolean); el = document.querySelector(".lesson-step") || page;
    }
    if (name === "settings") where = "Build settings";
    if (name === "math") where = "Math at a glance";
  }
  return { where, lessons, screen: String(el?.innerText || "").replace(/\n{3,}/g, "\n\n").slice(0, 6000) };
}
function showAsk(on) {
  askPanel.hidden = !on; askOpen.setAttribute("aria-expanded", String(on));
  if (on) { document.getElementById("ask-where").textContent = "Looking at: " + screenContext().where; askInput.focus(); } else askOpen.focus();
}
function addMsg(who, text) {
  askHistory.push({ who, text });
  askLog.insertAdjacentHTML("beforeend", `<p class="msg ${who}">${esc(text)}</p>`);
  askLog.scrollTop = askLog.scrollHeight;
  document.getElementById("ask-quick").hidden = true;
}
async function sendAsk(q) {
  q = String(q || "").trim(); if (!q) return;
  const ctx = screenContext();
  document.getElementById("ask-where").textContent = "Looking at: " + ctx.where;
  addMsg("me", q); askInput.value = "";
  const wait = document.createElement("p"); wait.className = "msg bot thinking"; wait.textContent = "Thinking…"; askLog.append(wait);
  askLog.scrollTop = askLog.scrollHeight;
  try {
    const r = await fetch("/api/ask", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: q, ...ctx, history: askHistory.slice(0, -1) }) });
    const d = await r.json(); wait.remove(); addMsg("bot", r.ok ? d.answer : d.error);
  } catch { wait.remove(); addMsg("bot", "Couldn't reach Quiz Prep. Is it still running?"); }
}
askOpen.onclick = () => showAsk(askPanel.hidden);
document.getElementById("ask-close").onclick = () => showAsk(false);
document.getElementById("ask-form").onsubmit = (e) => { e.preventDefault(); sendAsk(askInput.value); };
askInput.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendAsk(askInput.value); } });
document.getElementById("ask-quick").onclick = (e) => { const b = e.target.closest("button"); if (b) sendAsk(b.textContent); };
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !askPanel.hidden) showAsk(false); });

// ── Guide to 100%: the Ready ring starts it; one step at a time, each on its own page ──
const guideOn = () => store.get("qp.guide") === "on";
function startGuide() {
  store.set("qp.guide", "on");
  const r = Ready.readiness(progress, window.currentKit);
  if (r.next) showKitPage("quiz/" + r.next.tab);
}
function drawGuide() {
  const bar = document.getElementById("guide-bar"); if (!bar) return;
  const k = window.currentKit, r = k && Ready.readiness(progress, k);
  if (!r || !guideOn() || !r.next) { bar.hidden = true; return; }
  const i = Ready.READY_STEPS.indexOf(r.next), here = document.querySelector(".subtabs [aria-pressed=true]")?.dataset.sub;
  bar.hidden = false;
  bar.innerHTML = `<div class="guide-top"><span class="kicker">Step ${i + 1} of ${r.total} · ${r.pct}% ready</span>
      <button type="button" class="link" id="guide-pause">Pause guide</button></div>
    <p class="guide-step">${esc(r.next.label)}</p>
    <p class="dots" aria-hidden="true">${Ready.READY_STEPS.map((s) => `<span class="${r.doneIds.has(s.id) ? "done" : s === r.next ? "now" : ""}"></span>`).join("")}</p>
    <p class="guide-actions">${here === r.next.tab ? "" : `<button type="button" class="secondary" id="guide-there">Take me there →</button>`}
      <button type="button" class="primary" id="guide-done">I did this ✓</button></p>`;
  document.getElementById("guide-pause").onclick = () => { store.set("qp.guide", "off"); bar.hidden = true; };
  const there = document.getElementById("guide-there"); if (there) there.onclick = () => showKitPage("quiz/" + r.next.tab);
  document.getElementById("guide-done").onclick = () => {
    saveProgress({ plan: { ...(progress.plan || {}), [r.next.id]: true } });
    const after = Ready.readiness(progress, k).next;
    if (after) showKitPage("quiz/" + after.tab); else { store.set("qp.guide", "off"); showKitPage(""); }
  };
}

// ── Saved kits: every quiz's current kit plus the versions rebuilds replaced ──
const when = (iso) => iso ? new Date(iso).toLocaleString(undefined, { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : "unknown date";
async function drawSaved() {
  const box = document.getElementById("saved-list");
  let kits = [];
  try { kits = await (await fetch("/api/kits")).json(); } catch { box.innerHTML = "<p class='error'>Couldn't load your saved kits.</p>"; return; }
  if (!kits.length) { box.innerHTML = "<p class='muted'>No kits yet. Build one from Build settings.</p>"; return; }
  const groups = new Map();
  for (const k of kits) groups.set(k.quiz, [...(groups.get(k.quiz) || []), k]);
  box.innerHTML = [...groups].map(([quiz, rows]) => `<section class="card saved-quiz">
    <h3>${esc(String(quiz).replace(/\s*\(.*\)$/, ""))}${quiz === window.nextQuiz?.title ? ' <span class="pill">this week</span>' : ""}</h3>
    <p class="muted small">Lesson ${esc(rows[0].lessons.join(", ") || "?")}${rows[0].topics ? " · " + esc(rows[0].topics) : ""}</p>
    <ul class="saved-rows">${rows.map((k) => `<li><span><strong>${k.current ? "Current" : "Older"}</strong> · built ${esc(when(k.builtAt))}
        <span class="muted small">· ${k.cards} flashcards · ${k.problems}-problem worksheet${k.current ? "" : " · lessons " + esc(k.lessons.join(", "))}</span></span>
      <button type="button" class="secondary small" data-open-kit="${esc(k.id || "")}" data-quiz="${esc(k.quiz)}">Open</button></li>`).join("")}</ul></section>`).join("");
  box.onclick = async (e) => {
    const b = e.target.closest("[data-quiz]"); if (!b) return;
    const quiz = b.dataset.quiz, id = b.dataset.openKit, upcoming = (window.planner?.quizzes || []).find((x) => x.title === quiz);
    if (!id && quiz === window.nextQuiz?.title) { document.getElementById("kit-mode").hidden = true; await initKit(); return showKitPage("quiz/plan"); }
    if (!id && upcoming) { showKitMode(quiz); await initKit({ ...upcoming, lessons: [...upcoming.lessons] }); return showKitPage("quiz/plan"); }
    // a past quiz or an older version: show it as it was saved
    const k = await (await fetch("/api/kit?" + (id ? "id=" + encodeURIComponent(id) : "quiz=" + encodeURIComponent(quiz)))).json();
    if (!k) return;
    window.kitInfo = { quiz: k.quiz, lessons: k.lessons || [], topics: k.topics || "" };
    showKitMode(id ? `${String(k.quiz).replace(/\s*\(.*\)$/, "")} (older version from ${when(k.builtAt)})` : k.quiz);
    renderKit(k); showKitPage("quiz/plan");
  };
}
