"""Single-owner loopback review UI. Not an enterprise identity or tenant server."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
import hmac
import re

from .io import Busy, Closed, Unavailable, canonical, loads
from .service import RunService
from .diagnostics import error_response

PAGE = b'''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Control Plane | Review</title><link rel="stylesheet" href="/style.css">
<main><p class="eyebrow">HORISTUM / GITOPS AGENT CONTROL PLANE</p>
<h1>Review the exact candidate</h1>
<p>Single-owner review. Approval authorizes only the displayed binding.
The controller rechecks evidence and repository identity before merging.</p>
<label>Local review token <input id="token" type="password" autocomplete="off"></label>
<button id="load" type="button">Load decision</button>
<p id="message" role="status">Enter the token configured on the controller host.</p>
<section id="diagnostic-panel" hidden aria-live="polite"><h2>What happened</h2>
<p id="diagnostic-message"></p><p id="diagnostic-meta"></p>
<h3>Next steps</h3><ul id="diagnostic-steps"></ul>
<details><summary>Technical details and error location</summary><pre id="diagnostic-details"></pre></details></section>
<section><h2>Current decision</h2><dl id="facts"></dl>
<p>Inspect the complete decision below, including findings and verification evidence.</p>
<button id="approve" type="button" disabled>Approve this exact decision</button></section>
<section><h2>Review findings</h2><div id="findings"></div>
<h2>Verification evidence</h2><div id="evidence"></div>
<button id="load-diff" type="button" disabled>Load exact revision diff</button><pre id="diff"></pre></section>
<section><h2>Run controls</h2><p id="blocked-reason"></p>
<label>Reason for action <input id="reason" maxlength="1000"></label><div id="actions"></div>
<h2>Usage and recent activity</h2><pre id="usage"></pre><pre id="health"></pre></section>
<details><summary>Recent diagnostic log</summary><pre id="diagnostic-history"></pre></details>
<details open><summary>Complete human-decision.json</summary><pre id="document"></pre></details>
<p>The token is kept only in this page's memory. Reloading clears it.
This interface provides local owner authority, not named enterprise identities.</p>
</main><script src="/app.js"></script></html>'''

SCRIPT = b'''"use strict";
let shown = null;
const el = id => document.getElementById(id);
el("token").value = "";
async function api(path, options = {}) {
  const response = await fetch(path, {...options, cache: "no-store", credentials: "omit",
    headers: {"Authorization": "Bearer " + el("token").value, "Content-Type": "application/json"}});
  const value = await response.json();
  if (!response.ok) {
    const error = new Error(value.reason || "Request failed");
    error.diagnostic = value.diagnostic; throw error;
  }
  return value;
}
function renderDiagnostic(value) {
  el("diagnostic-panel").hidden = !value;
  if (!value) return;
  el("diagnostic-message").textContent = value.message;
  el("diagnostic-meta").textContent = [value.code, "Phase: " + (value.phase || "-"),
    "Operation: " + value.operation, "ID: " + value.id, value.at || "Current observation"].join(" | ");
  el("diagnostic-steps").replaceChildren();
  for (const step of value.next_steps || []) {
    const row = document.createElement("li"); row.textContent = step; el("diagnostic-steps").append(row);
  }
  el("diagnostic-details").textContent = JSON.stringify(value, null, 2);
}
function showError(error) {
  el("message").textContent = error.message + " Reload before acting.";
  if (error.diagnostic) renderDiagnostic(error.diagnostic);
}
el("token").addEventListener("input", () => { shown = null; el("approve").disabled = true; });
el("load-diff").addEventListener("click", async () => {
  if (!shown) return;
  try { const value = await api("/api/diff/" + shown.decision_hash); el("diff").textContent = value.diff; }
  catch (error) { showError(error); }
});
function details(target, title, value) {
  const box = document.createElement("details"), label = document.createElement("summary"), text = document.createElement("pre");
  label.textContent = title; text.textContent = JSON.stringify(value, null, 2);
  box.append(label, text); el(target).append(box);
}
el("load").addEventListener("click", async () => {
  shown = null; el("approve").disabled = true; el("document").textContent = "";
  el("facts").replaceChildren(); el("message").textContent = "Loading...";
  renderDiagnostic(null); el("diagnostic-history").textContent = "";
  for (const id of ["findings", "evidence", "actions"]) el(id).replaceChildren();
  el("diff").textContent = ""; el("load-diff").disabled = true;
  try {
    const value = await api("/api/decision");
    el("document").textContent = JSON.stringify(value, null, 2);
    renderDiagnostic(value.diagnostic);
    for (const name of ["run_id", "status", "phase", "paused", "head", "base", "risk", "binding", "decision_hash"]) {
      const term = document.createElement("dt"), detail = document.createElement("dd");
      term.textContent = name; detail.textContent = value[name] ?? "-";
      el("facts").append(term, detail);
    }
    shown = value; el("approve").disabled = !value.approvable;
    el("load-diff").disabled = !value.head;
    el("blocked-reason").textContent = value.reason || "No recorded blocker.";
    for (const [role, review] of Object.entries(value.reviews)) {
      const title = document.createElement("h3"), summary = document.createElement("p");
      title.textContent = role; summary.textContent = review.summary || "";
      el("findings").append(title, summary);
      for (const finding of review.findings || []) details("findings", finding.severity || "Finding", finding);
    }
    for (const [name, evidence] of Object.entries(value.evidence)) details("evidence", name, evidence);
    const ACTION_LABELS = {"retry-effect": "Retry unknown model call (possible additional cost)",
      "reconcile-effect": "Reconcile restored receipt (no new call)"};
    for (const name of value.actions) {
      const button = document.createElement("button"); button.type = "button";
      button.textContent = ACTION_LABELS[name] || name;
      button.addEventListener("click", async () => {
        if (!shown) return;
        if (name === "retry-effect" && !window.confirm("The previous model call may already have been charged. Authorize another call?")) return;
        if ((name === "cancel" || name === "replan") && !window.confirm("Apply " + name + " to this exact run state?")) return;
        const current = shown; shown = null; button.disabled = true; el("approve").disabled = true;
        try {
          await api("/api/action", {method: "POST", body: JSON.stringify({action: name,
            binding: current.pending_effect, decision_hash: current.decision_hash,
            reason: el("reason").value, accept_duplicate_cost: name === "retry-effect"})});
          el("load").click();
        } catch (error) { showError(error); }
      });
      el("actions").append(button);
    }
    api("/api/usage").then(report => { el("usage").textContent = JSON.stringify({reserved_calls: report.reserved_calls,
      recorded_calls: report.recorded_calls, unknown_outcomes: report.unknown_outcomes,
      reported_tokens: report.reported_tokens, recent_actions: value.recent_actions}, null, 2); })
      .catch(error => { el("usage").textContent = error.message; });
    api("/api/status").then(status => { el("health").textContent = JSON.stringify(status, null, 2); })
      .catch(error => { el("health").textContent = error.message; });
    api("/api/diagnostics").then(report => { el("diagnostic-history").textContent = JSON.stringify(report, null, 2); })
      .catch(error => { el("diagnostic-history").textContent = error.message; });
    el("message").textContent = value.approvable ? "Waiting for your decision." : "No approvable decision in this state.";
  } catch (error) { showError(error); }
});
el("approve").addEventListener("click", async () => {
  if (!shown || !shown.approvable) return;
  const current = shown; shown = null; el("approve").disabled = true;
  try {
    await api("/api/approve", {method: "POST", body: JSON.stringify({binding: current.binding, decision_hash: current.decision_hash})});
    el("message").textContent = "Approval recorded. The supervisor can continue and recheck gates.";
  } catch (error) { showError(error); }
});'''

STYLE = b'''body{margin:0;background:#101923;color:#e6edf3;font:16px/1.6 system-ui,sans-serif}
main{max-width:1000px;margin:auto;padding:40px 24px}.eyebrow{color:#65ddbc;letter-spacing:.12em;font-size:12px}
h1{font-size:36px;line-height:1.2}section,details{padding:20px;margin:24px 0;background:#192735;border:1px solid #385060;border-radius:12px}
input,button{font:inherit;padding:10px 14px;margin:8px 8px 8px 0;border-radius:6px;border:1px solid #668291}
input{background:#101923;color:white}button{background:#65ddbc;color:#10251e;cursor:pointer}button:disabled{opacity:.45;cursor:default}
dt{font-weight:bold;color:#9eafbd}dd{margin:0 0 12px;overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}
#message{color:#65ddbc}summary{cursor:pointer}[hidden]{display:none!important}
#diagnostic-panel{border-color:#e5a458}#diagnostic-message{font-size:18px}
#diagnostic-meta{color:#b8c5ce;font-size:13px;overflow-wrap:anywhere}'''


def create_server(root, token, *, port=8765):
    if (not isinstance(token, str) or not 32 <= len(token) <= 512
            or any(ord(c) < 33 or ord(c) > 126 for c in token)):
        raise Closed("Review requires a private printable token of at least 32 characters")
    service = RunService(root)

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def log_message(self, *_):
            pass  # Never log authentication headers or request bodies.

        def send(self, status, value, content_type="application/json"):
            data = value if isinstance(value, bytes) else canonical(value)
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
            self.end_headers()
            self.wfile.write(data)

        def dispatch(self):
            host = "127.0.0.1:" + str(self.server.server_port)
            if self.headers.get_all("Host") != [host]:
                return self.send(403, {"reason": "Invalid local host"})
            origins = self.headers.get_all("Origin", [])
            if origins and origins != ["http://" + host]:
                return self.send(403, {"reason": "Cross-origin request forbidden"})
            assets = {"/": (PAGE, "text/html; charset=utf-8"),
                      "/app.js": (SCRIPT, "text/javascript; charset=utf-8"),
                      "/style.css": (STYLE, "text/css; charset=utf-8")}
            if self.command == "GET" and self.path in assets:
                return self.send(200, *assets[self.path])
            auth = self.headers.get_all("Authorization", [])
            if len(auth) != 1 or not hmac.compare_digest(auth[0].encode(), ("Bearer " + token).encode()):
                return self.send(401, {"reason": "Review token required"})
            if self.command == "GET" and self.path == "/api/decision":
                return self.send(200, service.decision())
            if self.command == "GET" and self.path in {"/api/status", "/api/usage", "/api/diagnostics"}:
                return self.send(200, getattr(service, self.path.rsplit("/", 1)[-1])())
            if self.command == "GET" and re.fullmatch(r"/api/diff/[0-9a-f]{64}", self.path):
                return self.send(200, service.diff(self.path.rsplit("/", 1)[-1]))
            if self.command != "POST" or self.path not in {"/api/approve", "/api/action"}:
                return self.send(404, {"reason": "Unknown review operation"})
            lengths = self.headers.get_all("Content-Length", [])
            if (len(lengths) != 1 or not lengths[0].isdigit() or not 1 <= int(lengths[0]) <= 2048
                    or self.headers.get("Transfer-Encoding")
                    or self.headers.get_all("Content-Type") != ["application/json"]):
                return self.send(400, {"reason": "Expected bounded JSON body"})
            value = loads(self.rfile.read(int(lengths[0])))
            if self.path == "/api/action":
                if (not isinstance(value, dict) or set(value) != {"action", "binding", "decision_hash", "reason", "accept_duplicate_cost"}
                        or not isinstance(value["action"], str)
                        or value["action"] not in {"pause", "continue", "retry", "retry-effect", "reconcile-effect", "reconcile", "replan", "cancel"}
                        or not isinstance(value["decision_hash"], str) or not re.fullmatch(r"[0-9a-f]{64}", value["decision_hash"])
                        or not isinstance(value["reason"], str) or len(value["reason"]) > 1000
                        or type(value["accept_duplicate_cost"]) is not bool
                        or (value["binding"] is not None and (not isinstance(value["binding"], str)
                            or not re.fullmatch(r"[0-9a-f]{64}", value["binding"])))
                        or value["action"] == "retry-effect" and not value["accept_duplicate_cost"]):
                    return self.send(400, {"reason": "Exact action binding and explicit cost acknowledgement required"})
                return self.send(200, service.act(value["action"], value["decision_hash"],
                    binding=value["binding"], reason=value["reason"]))
            if (not isinstance(value, dict) or set(value) != {"binding", "decision_hash"}
                    or any(not isinstance(v, str) or len(v) != 64 for v in value.values())):
                return self.send(400, {"reason": "Exact binding and decision hash required"})
            return self.send(200, service.approve(value["binding"], value["decision_hash"]))

        def handle_operation(self):
            try:
                self.dispatch()
            except Busy:
                self.send(409, {"reason": "Run busy; retry after the active tick"})
            except Exception as exc:
                status = 503 if isinstance(exc, Unavailable) else 409 if isinstance(exc, (Closed, ValueError)) else 500
                self.send(status, error_response(root, exc, operation="review:" + self.command + " " + self.path, secrets=(token,)))

        do_GET = handle_operation
        do_POST = handle_operation

    return HTTPServer(("127.0.0.1", port), Handler)
