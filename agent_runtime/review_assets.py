"""Local operator presentation; all untrusted content is inserted as text."""

PAGE = b'''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Control Plane | Run overview</title><link rel="stylesheet" href="/style.css">
<main><p class="eyebrow">HORISTUM / GITOPS AGENT CONTROL PLANE</p>
<h1>Understand and review this run</h1>
<p>Progress, recovery and the exact candidate in one place.</p>
<label>Local review token <input id="token" type="password" autocomplete="off"></label>
<button id="load" type="button">Load run</button>
<p id="message" role="status">Enter the token configured on the controller host.</p>
<div id="overview" hidden>
<section><h2>Current situation</h2><p id="run-summary" class="lead"></p>
<dl id="health" class="facts"></dl><ul id="warnings"></ul>
<h3>Next step</h3><p id="next-description"></p><p id="next-condition"></p>
<pre id="next-command"></pre><ul id="guidance"></ul></section>
<section id="diagnostic-panel" hidden aria-live="polite"><h2>Why it stopped</h2>
<p id="diagnostic-message"></p><p id="diagnostic-meta"></p>
<details><summary>Technical details and error location</summary><pre id="diagnostic-details"></pre></details></section>
<section><h2>Where the result lives</h2><dl id="product" class="facts"></dl><p id="product-note"></p></section>
<section><h2>Workflow</h2><p id="workflow-modifiers"></p>
<ol id="workflow" class="route"></ol><p id="workflow-note"></p>
<h3>Recent transitions</h3><p id="timeline-note"></p><ol id="timeline" class="timeline"></ol></section>
<section><h2>Review the exact candidate</h2><dl id="facts" class="facts"></dl>
<p>Approval authorizes only the displayed binding. The controller rechecks evidence and repository identity before merging.</p>
<button id="approve" type="button" disabled>Approve this exact decision</button>
<h3>Review findings</h3><div id="findings"></div>
<h3>Verification evidence</h3><div id="evidence"></div>
<button id="load-diff" type="button" disabled>Load exact revision diff</button><pre id="diff"></pre></section>
<section><h2>Other owner actions</h2><p>Conditions are checked again when you act. Commands below do not run automatically.</p>
<label>Reason for action <input id="reason" maxlength="1000"></label><div id="actions"></div></section>
<section><h2>Model usage</h2><dl id="usage" class="facts"></dl>
<p>Reserved calls include uncertain outcomes. Provider usage is not an invoice.</p>
<h3>Recent owner actions</h3><ol id="owner-history" class="timeline"></ol></section>
<section><h2>Recent diagnostics</h2><p>Historical events may already be resolved. The current situation is shown above.</p>
<div id="diagnostic-history"></div></section>
<details><summary>Complete decision JSON</summary><pre id="document"></pre></details>
<p id="observation-note"></p></div>
<p>The token is kept only in this page's memory. Reloading clears it.
This interface provides local owner authority, not named enterprise identities.</p>
</main><script src="/app.js"></script></html>'''

SCRIPT = b'''"use strict";
let shown = null, generation = 0;
const el = id => document.getElementById(id);
const text = value => value == null ? "-" : typeof value === "object" ? JSON.stringify(value) : String(value);
function node(tag, value, className) {
  const result = document.createElement(tag); result.textContent = text(value);
  if (className) result.className = className;
  return result;
}
function facts(id, rows) {
  el(id).replaceChildren();
  for (const [label, value] of rows) el(id).append(node("dt", label), node("dd", value));
}
function list(id, rows) {
  el(id).replaceChildren(...rows.map(value => node("li", value)));
}
function details(target, title, value) {
  const box = document.createElement("details");
  box.append(node("summary", title), node("pre", JSON.stringify(value, null, 2))); target.append(box);
}
function invalidate() {
  shown = null; el("approve").disabled = true; el("load-diff").disabled = true;
  el("actions").querySelectorAll("button").forEach(button => { button.disabled = true; });
}
async function api(path, options = {}) {
  const response = await fetch(path, {...options, cache: "no-store", credentials: "omit",
    headers: {"Authorization": "Bearer " + el("token").value, "Content-Type": "application/json"}});
  const value = await response.json();
  if (!response.ok) {
    const error = new Error(value.reason || "Request failed"); error.diagnostic = value.diagnostic; throw error;
  }
  return value;
}
function renderDiagnostic(value) {
  el("diagnostic-panel").hidden = !value;
  if (!value) return;
  el("diagnostic-message").textContent = value.message;
  el("diagnostic-meta").textContent = [value.code, "Phase: " + text(value.phase),
    "Operation: " + text(value.operation), "ID: " + text(value.id), value.at || "Current observation"].join(" | ");
  el("diagnostic-details").textContent = JSON.stringify(value, null, 2);
}
function showError(error) {
  invalidate(); el("message").textContent = error.message + " Reload before acting.";
  el("next-command").textContent = ""; el("next-command").hidden = true;
  el("next-description").textContent = "Reload the run before choosing another action.";
  el("next-condition").textContent = "";
  if (error.diagnostic) { el("overview").hidden = false; renderDiagnostic(error.diagnostic); }
}
function render(report) {
  const value = report.decision, status = report.status, product = status.product, route = report.workflow;
  el("overview").hidden = false; el("run-summary").textContent = report.summary;
  facts("health", [["Status", status.status], ["Paused", status.paused], ["Phase", report.phase_label + " (" + status.phase + ")"],
    ["Item", status.item], ["Run", status.run_id], ["Revision", status.revision], ["Updated", status.updated_at]]);
  list("warnings", report.warnings); list("guidance", report.guidance);
  const next = report.next_action;
  el("next-description").textContent = next ? next.description :
    ["COMPLETED", "CANCELLED"].includes(status.status) ? "No recovery action is needed." : "Inspect the cause and choose a conditional owner action below.";
  el("next-condition").textContent = next ? next.condition : "";
  el("next-command").textContent = next ? next.command : ""; el("next-command").hidden = !next;
  renderDiagnostic(report.diagnostic);
  facts("product", [["Source checkout", product.source_checkout], ["Run repository", product.repository],
    ["Local base ref", product.base_ref], ["Local base ref SHA", product.base_ref_sha],
    ["Candidate / observed head", status.head], ["Merge commit", status.merge_sha],
    ...(product.inspection_error ? [["Inspection unavailable", product.inspection_error]] : [])]);
  el("product-note").textContent = product.note;
  el("workflow-modifiers").textContent = route.phases.length ?
    "Risk: " + route.risk + " | Graph: " + route.level + " | Adaptive: " + route.adaptive +
    " | Critical: " + route.critical + " | Challenge: " + route.challenge +
    (route.risk_gate_return ? " | After risk gates: " + route.risk_gate_return : "") : "No active item.";
  el("workflow").replaceChildren();
  for (const phase of route.phases) {
    const row = document.createElement("li");
    row.append(node("strong", phase.label), node("small", phase.id + (phase.current ? " / CURRENT" : phase.resume ? " / RESUME HERE" : "")));
    if (phase.current || phase.resume) row.className = "current";
    if (phase.current) row.setAttribute("aria-current", "step");
    el("workflow").append(row);
  }
  el("workflow-note").textContent = route.note; el("timeline-note").textContent = report.timeline_note;
  list("timeline", report.timeline.map(row => row.phase + " -> " + row.next + " | " + row.status +
    (row.diagnostic_id ? " | diagnostic " + row.diagnostic_id : "")));
  if (!report.timeline.length) list("timeline", ["No transitions recorded yet."]);
  facts("facts", [["Risk", value.risk], ["Base", value.base], ["Candidate head", value.head],
    ["Binding", value.binding], ["Decision hash", value.decision_hash]]);
  el("document").textContent = JSON.stringify(value, null, 2);
  el("findings").replaceChildren();
  for (const [role, review] of Object.entries(value.reviews)) {
    const card = document.createElement("article");
    card.append(node("h4", role + " / " + text(review.verdict)), node("p", review.summary));
    const findings = document.createElement("ul");
    for (const finding of review.findings || []) findings.append(node("li", finding.severity + " / " + finding.kind + ": " + finding.description));
    card.append(findings); details(card, "Complete review data", review); el("findings").append(card);
  }
  if (!Object.keys(value.reviews).length) el("findings").append(node("p", "No reviews in the current execution frame."));
  el("evidence").replaceChildren();
  for (const [name, proof] of Object.entries(value.evidence)) {
    const card = document.createElement("article");
    card.append(node("h4", name), node("p", report.evidence_summaries[name]));
    details(card, "Exact verification observations", proof); el("evidence").append(card);
  }
  if (!Object.keys(value.evidence).length) el("evidence").append(node("p", "No verification evidence in the current decision. Completed attempts remain in the run archive."));
  el("actions").replaceChildren();
  for (const action of report.actions) {
    if (action.id === "approve" || !value.actions.includes(action.id)) continue;
    const card = document.createElement("article"), button = node("button", action.id);
    button.type = "button"; button.disabled = !action.enabled;
    button.addEventListener("click", () => act(action.id));
    card.append(node("h3", action.description), node("p", action.condition), node("code", action.command), button);
    el("actions").append(card);
  }
  facts("usage", [["Reserved calls", report.usage.reserved_calls], ["Recorded calls", report.usage.recorded_calls],
    ["Unknown outcomes", report.usage.unknown_outcomes], ["Input tokens", (report.usage.reported_tokens || {}).input_tokens],
    ["Output tokens", (report.usage.reported_tokens || {}).output_tokens]]);
  list("owner-history", report.recent_actions.map(row => row.at + " | " + row.action + (row.reason ? " | " + row.reason : "")));
  el("diagnostic-history").replaceChildren();
  for (const event of report.diagnostics.events) {
    const card = document.createElement("article");
    card.append(node("h3", event.code), node("p", event.message),
      node("small", text(event.at) + " | " + text(event.phase) + " | ID " + text(event.id)));
    details(card, "Diagnostic details", event); el("diagnostic-history").append(card);
  }
  if (!report.diagnostics.events.length) el("diagnostic-history").append(node("p", "No diagnostic events available."));
  el("observation-note").textContent = report.observation_note;
  shown = value; el("approve").disabled = !value.approvable; el("load-diff").disabled = !value.head;
}
async function load() {
  const request = ++generation; invalidate();
  el("overview").hidden = true; el("diff").textContent = ""; el("message").textContent = "Loading...";
  try {
    const report = await api("/api/explain"); if (request !== generation) return;
    render(report); el("message").textContent = "Run loaded. Review the conditions before acting.";
  } catch (error) { if (request === generation) showError(error); }
}
async function act(name) {
  if (!shown) return;
  if (name === "retry-effect" && !window.confirm("The previous model call may already have been charged. Authorize another call?")) return;
  if (["cancel", "replan"].includes(name) && !window.confirm("Apply " + name + " to this exact run state?")) return;
  const current = shown, request = ++generation; invalidate();
  try {
    await api("/api/action", {method: "POST", body: JSON.stringify({action: name,
      binding: current.pending_effect, decision_hash: current.decision_hash, reason: el("reason").value,
      accept_duplicate_cost: name === "retry-effect"})});
    if (request === generation) await load();
  } catch (error) { if (request === generation) showError(error); }
}
el("token").value = "";
el("token").addEventListener("input", () => { ++generation; invalidate(); el("overview").hidden = true; });
el("load").addEventListener("click", load);
el("load-diff").addEventListener("click", async () => {
  if (!shown) return;
  const request = generation, decision = shown.decision_hash;
  try {
    const result = await api("/api/diff/" + decision);
    if (request === generation && shown && shown.decision_hash === decision) el("diff").textContent = result.diff;
  } catch (error) { if (request === generation) showError(error); }
});
el("approve").addEventListener("click", async () => {
  if (!shown || !shown.approvable) return;
  const current = shown, request = ++generation; invalidate();
  try {
    await api("/api/approve", {method: "POST", body: JSON.stringify({binding: current.binding, decision_hash: current.decision_hash})});
    if (request === generation) await load();
  } catch (error) { if (request === generation) showError(error); }
});'''

STYLE = b'''body{margin:0;background:#101923;color:#e6edf3;font:16px/1.6 system-ui,sans-serif}
main{max-width:1100px;margin:auto;padding:32px 24px}.eyebrow{color:#65ddbc;letter-spacing:.1em;font-size:12px}
h1{font-size:34px;line-height:1.2}h2{margin-top:0}h3{font-size:18px}h4{margin:0}.lead{font-size:20px}
section{padding:24px;margin:24px 0;background:#192735;border:1px solid #385060;border-radius:12px}
details{padding:12px;margin:12px 0;border:1px solid #385060;border-radius:8px}
input,button{font:inherit;padding:10px 14px;margin:8px 8px 8px 0;border-radius:6px;border:1px solid #668291}
input{background:#101923;color:white;max-width:100%;box-sizing:border-box}button{background:#65ddbc;color:#10251e;cursor:pointer}
button:disabled{opacity:.45;cursor:default}:focus-visible{outline:3px solid #eed07b;outline-offset:3px}
dt{font-weight:600;color:#afc2d0}dd{margin:0;overflow-wrap:anywhere}.facts{display:grid;grid-template-columns:190px minmax(0,1fr);gap:8px 20px}
pre,code{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}pre{background:#101923;padding:12px;border-radius:6px}
article{margin:16px 0;padding:16px;border:1px solid #385060;border-radius:8px}article code{display:block}
small{display:block;color:#afc2d0;overflow-wrap:anywhere}.route{padding:0;list-style-position:inside;display:grid;grid-template-columns:repeat(auto-fit,minmax(215px,1fr));gap:10px}
.route li{padding:12px;border:1px solid #385060;border-radius:8px}.route .current{border:2px solid #65ddbc;background:#183a36}
.route strong{font-size:14px}.timeline{padding-left:24px}.timeline li{padding:6px 0;overflow-wrap:anywhere}
#message{color:#65ddbc}summary{cursor:pointer}[hidden]{display:none!important}#warnings{color:#eed07b}
#diagnostic-panel{border-color:#e5a458}#diagnostic-message{font-size:18px}#diagnostic-meta{color:#bfccd6;font-size:13px;overflow-wrap:anywhere}
@media(max-width:600px){main{padding:20px 12px}section{padding:16px}.facts{grid-template-columns:1fr;gap:4px}.facts dd{margin-bottom:12px}}'''
