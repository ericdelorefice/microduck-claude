"""The playground's single-page UI (served at ``/``). One self-contained HTML string."""

from __future__ import annotations

PAGE_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Microduck Playground</title>
<style>
  :root { --bg:#0e0f13; --panel:#15171e; --line:#2a2d38; --fg:#e6e8ee; --muted:#8b90a0; --accent:#ff7a1a; }
  * { box-sizing: border-box; }
  body { margin:0; font-family: ui-sans-serif, system-ui, -apple-system, sans-serif; background:var(--bg); color:var(--fg); }
  header { padding:12px 18px; border-bottom:1px solid var(--line); display:flex; align-items:baseline; gap:10px; }
  header b { font-size:16px; } header span { color:var(--muted); font-size:13px; }
  .wrap { display:flex; gap:16px; padding:16px; flex-wrap:wrap; }
  .stage { flex:1 1 340px; background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:10px; min-height:340px; display:flex; flex-direction:column; align-items:center; justify-content:center; }
  .side { flex:1 1 340px; display:flex; flex-direction:column; gap:12px; }
  .card { background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:12px; }
  .status { display:flex; gap:16px; flex-wrap:wrap; color:var(--muted); font-size:13px; }
  .status b { color:var(--fg); font-weight:600; }
  #log { height:190px; overflow:auto; display:flex; flex-direction:column; gap:6px; font-size:14px; }
  .msg { padding:6px 10px; border-radius:10px; max-width:92%; }
  .me { align-self:flex-end; background:#273049; }
  .duck { align-self:flex-start; background:#20242e; }
  .row { display:flex; gap:8px; }
  input[type=text] { flex:1; background:#0b0c10; border:1px solid var(--line); color:var(--fg); border-radius:8px; padding:9px 11px; font-size:14px; }
  button { background:#20242e; border:1px solid var(--line); color:var(--fg); border-radius:8px; padding:8px 12px; cursor:pointer; font-size:13px; }
  button:hover { border-color:var(--accent); }
  button.primary { background:var(--accent); color:#111; border-color:var(--accent); font-weight:600; }
  .gestures { display:flex; flex-wrap:wrap; gap:6px; }
  .chip { color:var(--accent); font-size:13px; min-height:18px; margin-top:6px; }
  .modal-bg { position:fixed; inset:0; background:rgba(0,0,0,.55); display:none; align-items:center; justify-content:center; }
  .modal { background:var(--panel); border:1px solid var(--accent); border-radius:12px; padding:18px; max-width:380px; }
  .modal p { margin:0 0 14px; } .modal .row { justify-content:flex-end; }
  h3 { margin:0 0 8px; font-size:12px; color:var(--muted); text-transform:uppercase; letter-spacing:.05em; }
</style>
</head>
<body>
<header><b>&#129414; Microduck Playground</b><span>a hardware-free test area &mdash; the fake duck reacts live</span></header>
<div class="wrap">
  <div class="stage">
    <svg id="stage" viewBox="0 0 300 300" width="300" height="300" aria-label="duck">
      <g id="body">
        <ellipse cx="150" cy="215" rx="72" ry="56" fill="#ece3d0"/>
        <ellipse cx="120" cy="266" rx="17" ry="8" fill="#ff7a1a"/>
        <ellipse cx="180" cy="266" rx="17" ry="8" fill="#ff7a1a"/>
      </g>
      <g id="head">
        <circle cx="150" cy="120" r="58" fill="#f3ecdd"/>
        <circle cx="130" cy="112" r="7" fill="#1c1f27"/>
        <circle cx="170" cy="112" r="7" fill="#1c1f27"/>
        <polygon points="132,134 168,134 150,149" fill="#ff7a1a"/>
        <polygon id="beak" points="134,137 166,137 150,149" fill="#e86a0c"/>
      </g>
      <text id="note" x="214" y="78" font-size="24" fill="#ff7a1a" opacity="0">&#9834;</text>
    </svg>
    <div class="chip" id="chip">&nbsp;</div>
  </div>
  <div class="side">
    <div class="card status">
      <div>sound <b id="s-sound">&mdash;</b></div>
      <div>behavior <b id="s-beh">&mdash;</b></div>
      <div>beak <b id="s-mouth">0%</b></div>
      <div>driving <b id="s-drive">no</b></div>
      <div>events <b id="s-ev">0</b></div>
    </div>
    <div class="card">
      <h3>Talk to the duck</h3>
      <div id="log"></div>
      <div class="row" style="margin-top:8px">
        <input id="text" type="text" placeholder="Say something (needs Anthropic credentials)">
        <button class="primary" onclick="send()">Send</button>
      </div>
    </div>
    <div class="card">
      <h3>Preview gestures (no API key needed)</h3>
      <div class="gestures" id="gestures"></div>
    </div>
  </div>
</div>
<div class="modal-bg" id="modalbg">
  <div class="modal">
    <h3>Confirm action</h3>
    <p id="modaltext"></p>
    <div class="row">
      <button onclick="confirmAction(false)">Deny</button>
      <button class="primary" onclick="confirmAction(true)">Allow</button>
    </div>
  </div>
</div>
<script>
const $ = (id) => document.getElementById(id);
let pendingId = null, lastEvents = -1, lastSound = null;
const deg = (r) => (r || 0) * 57.2958;

function render(d) {
  const hx = (d.head_yaw || 0) * 40, hy = -(d.head_pitch || 0) * 40;
  $("head").setAttribute("transform", `translate(${hx},${hy}) rotate(${deg(d.head_roll)},150,120)`);
  const bz = -(d.body_z || 0) * 400, br = deg(d.body_roll);
  $("body").setAttribute("transform", `translate(0,${bz}) rotate(${br},150,215)`);
  const open = Math.max(0, Math.min(1, d.mouth || 0)) * 15;
  $("beak").setAttribute("points", `134,137 166,137 150,${149 + open}`);
  $("s-sound").textContent = d.last_sound || "\\u2014";
  $("s-beh").textContent = d.last_behavior || "\\u2014";
  $("s-mouth").textContent = Math.round((d.mouth || 0) * 100) + "%";
  $("s-drive").textContent = d.driving ? "yes" : "no";
  $("s-ev").textContent = d.events || 0;
  if (d.events !== lastEvents && d.last_sound && d.last_sound !== lastSound) {
    $("note").setAttribute("opacity", "1");
    $("chip").textContent = "\\u266a " + d.last_sound;
    setTimeout(() => $("note").setAttribute("opacity", "0"), 450);
  }
  lastEvents = d.events; lastSound = d.last_sound;
}

async function poll() {
  try {
    const j = await (await fetch("/state")).json();
    render(j.duck);
    if (j.pending) showModal(j.pending); else hideModal();
  } catch (e) {}
}
function showModal(p) {
  if (pendingId === p.id) return;
  pendingId = p.id; $("modaltext").textContent = p.prompt;
  $("modalbg").style.display = "flex";
}
function hideModal() { pendingId = null; $("modalbg").style.display = "none"; }
async function confirmAction(allow) {
  const id = pendingId; hideModal();
  await post("/confirm", { id, allow });
}
function addMsg(who, text) {
  const d = document.createElement("div");
  d.className = "msg " + (who === "me" ? "me" : "duck");
  d.textContent = text; $("log").appendChild(d); $("log").scrollTop = 1e9;
}
async function post(path, body) {
  return (await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body) })).json();
}
async function send() {
  const t = $("text").value.trim(); if (!t) return;
  $("text").value = ""; addMsg("me", t);
  try {
    const j = await post("/say", { text: t });
    (j.replies || []).forEach((x) => addMsg("duck", x));
    if (j.refused && !(j.replies || []).length) addMsg("duck", "(declined)");
  } catch (e) { addMsg("duck", "(error talking to the duck)"); }
}
async function loadGestures() {
  try {
    const j = await (await fetch("/gestures")).json();
    (j.gestures || []).forEach((name) => {
      const b = document.createElement("button");
      b.textContent = name;
      b.onclick = () => post("/gesture", { name });
      $("gestures").appendChild(b);
    });
  } catch (e) {}
}
$("text").addEventListener("keydown", (e) => { if (e.key === "Enter") send(); });
loadGestures();
setInterval(poll, 150);
poll();
</script>
</body>
</html>
"""
