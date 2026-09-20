"""Single-owner loopback review UI. Not an enterprise identity or tenant server."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
import hmac

from .io import Busy, Closed, Unavailable, canonical, loads
from .service import RunService

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
<section><h2>Current decision</h2><dl id="facts"></dl>
<p>Inspect the complete decision below, including findings and verification evidence.</p>
<button id="approve" type="button" disabled>Approve this exact decision</button></section>
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
  if (!response.ok) throw new Error(value.reason || "Request failed");
  return value;
}
el("token").addEventListener("input", () => { shown = null; el("approve").disabled = true; });
el("load").addEventListener("click", async () => {
  shown = null; el("approve").disabled = true; el("document").textContent = "";
  el("facts").replaceChildren(); el("message").textContent = "Loading...";
  try {
    const value = await api("/api/decision");
    el("document").textContent = JSON.stringify(value, null, 2);
    for (const name of ["run_id", "status", "head", "base", "risk", "binding", "decision_hash"]) {
      const term = document.createElement("dt"), detail = document.createElement("dd");
      term.textContent = name; detail.textContent = value[name] ?? "-";
      el("facts").append(term, detail);
    }
    shown = value; el("approve").disabled = !value.approvable;
    el("message").textContent = value.approvable ? "Waiting for your decision." : "No approvable decision in this state.";
  } catch (error) { el("message").textContent = error.message; }
});
el("approve").addEventListener("click", async () => {
  if (!shown || !shown.approvable) return;
  const current = shown; shown = null; el("approve").disabled = true;
  try {
    await api("/api/approve", {method: "POST", body: JSON.stringify({binding: current.binding, decision_hash: current.decision_hash})});
    el("message").textContent = "Approval recorded. Resume the controller to recheck gates and continue.";
  } catch (error) { el("message").textContent = error.message + " Reload the decision before trying again."; }
});'''

STYLE = b'''body{margin:0;background:#101923;color:#e6edf3;font:16px/1.6 system-ui,sans-serif}
main{max-width:1000px;margin:auto;padding:40px 24px}.eyebrow{color:#65ddbc;letter-spacing:.12em;font-size:12px}
h1{font-size:36px;line-height:1.2}section,details{padding:20px;margin:24px 0;background:#192735;border:1px solid #385060;border-radius:12px}
input,button{font:inherit;padding:10px 14px;margin:8px 8px 8px 0;border-radius:6px;border:1px solid #668291}
input{background:#101923;color:white}button{background:#65ddbc;color:#10251e;cursor:pointer}button:disabled{opacity:.45;cursor:default}
dt{font-weight:bold;color:#9eafbd}dd{margin:0 0 12px;overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}
#message{color:#65ddbc}summary{cursor:pointer}'''


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
            if self.command != "POST" or self.path != "/api/approve":
                return self.send(404, {"reason": "Unknown review operation"})
            lengths = self.headers.get_all("Content-Length", [])
            if (len(lengths) != 1 or not lengths[0].isdigit() or not 1 <= int(lengths[0]) <= 2048
                    or self.headers.get("Transfer-Encoding")
                    or self.headers.get_all("Content-Type") != ["application/json"]):
                return self.send(400, {"reason": "Expected bounded JSON body"})
            value = loads(self.rfile.read(int(lengths[0])))
            if (not isinstance(value, dict) or set(value) != {"binding", "decision_hash"}
                    or any(not isinstance(v, str) or len(v) != 64 for v in value.values())):
                return self.send(400, {"reason": "Exact binding and decision hash required"})
            return self.send(200, service.approve(value["binding"], value["decision_hash"]))

        def handle_operation(self):
            try:
                self.dispatch()
            except Busy:
                self.send(409, {"reason": "Run busy; retry after the active tick"})
            except (Closed, ValueError):
                self.send(409, {"reason": "Decision unavailable or changed; reload and inspect controller status"})
            except Unavailable:
                self.send(503, {"reason": "External service unavailable"})
            except (OSError, KeyError, TypeError):
                self.send(500, {"reason": "Cannot read the run; inspect controller status"})

        do_GET = handle_operation
        do_POST = handle_operation

    return HTTPServer(("127.0.0.1", port), Handler)
