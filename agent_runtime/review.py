"""Single-owner loopback review UI. Not an enterprise identity or tenant server."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
import hmac
import re

from .io import Busy, Closed, Unavailable, canonical, loads
from .service import RunService
from .diagnostics import error_response
from .review_assets import PAGE, SCRIPT, STYLE


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
            if self.command == "GET" and self.path in {"/api/status", "/api/usage", "/api/diagnostics", "/api/explain"}:
                return self.send(200, getattr(service, self.path.rsplit("/", 1)[-1])())
            if self.command == "GET" and re.fullmatch(r"/api/diff/[0-9a-f]{64}", self.path):
                return self.send(200, service.diff(self.path.rsplit("/", 1)[-1]))
            if self.command != "POST" or self.path not in {"/api/approve", "/api/approve-work", "/api/action"}:
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
                        or value["action"] not in {"pause", "continue", "reverify", "retry-effect", "reconcile-effect", "reconcile", "replan", "cancel"}
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
            approve = service.approve_work if self.path == "/api/approve-work" else service.approve
            return self.send(200, approve(value["binding"], value["decision_hash"]))

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
