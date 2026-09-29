"""Official stdio app-server transport with controller-owned tools and durable turn identity."""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
import selectors
import signal
import subprocess
import tempfile
import time
from .capabilities import DISABLED_FEATURES, inspect_cli
from .protocol import ToolInputError, WorkerError, WorkerIndeterminate, atomic, canonical, fingerprint, loads, read_record, validate_profile

CONFIG = {"forced_login_method": "chatgpt", "model_provider": "openai", "approval_policy": "never",
          "web_search": "disabled", "mcp_servers": {}, "features.code_mode.enabled": False,
          "hooks": {name: [] for name in ("PreToolUse", "PermissionRequest", "PostToolUse", "PreCompact", "PostCompact",
              "SessionStart", "SessionEnd", "UserPromptSubmit", "SubagentStart", "SubagentStop", "Stop", "Interrupt")},
          "default_permissions": "worker_broker", "permissions.worker_broker.filesystem": {":minimal": "read", ":workspace_roots": "read"},
          "permissions.worker_broker.network.enabled": False,
          **{"features." + name: False for name in DISABLED_FEATURES}}
FORBIDDEN_ITEMS = {"commandExecution", "fileChange", "mcpToolCall", "webSearch", "collabAgentToolCall",
                   "imageGeneration", "localShellCall", "computerUse", "browserUse"}

class _Connection:
    def __init__(self, argv, cwd, env, profile):
        self.profile = profile; self.deadline = time.monotonic() + profile["timeout_seconds"]
        self.selector = selectors.DefaultSelector(); self.buffers = {"out": bytearray(), "err": bytearray()}
        self.output_bytes = 0; self.identifier = 0
        try:
            self.process = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        except OSError as exc:
            raise WorkerError("Worker process could not start") from exc
        for name, stream in (("out", self.process.stdout), ("err", self.process.stderr)):
            os.set_blocking(stream.fileno(), False)
            self.selector.register(stream, selectors.EVENT_READ, name)

    def close(self):
        if self.process.poll() is None:
            self.process.stdin.close()
            try: self.process.wait(timeout=2)
            except subprocess.TimeoutExpired: pass
        if self.process.poll() is None:
            try: os.killpg(self.process.pid, signal.SIGTERM)
            except ProcessLookupError: pass
            try: self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try: os.killpg(self.process.pid, signal.SIGKILL)
                except ProcessLookupError: pass
                self.process.wait()
        self.selector.close()
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr): stream.close()

    def send(self, value):
        raw = canonical(value) + b"\n"
        if len(raw) > self.profile["max_frame_bytes"]:
            raise WorkerError("Outgoing worker frame exceeds bound")
        # A stopped/malicious server must not block the controller on pipe writes.
        fd = self.process.stdin.fileno(); os.set_blocking(fd, False)
        offset = 0
        import select
        while offset < len(raw):
            remaining = self.deadline - time.monotonic()
            if remaining <= 0: raise WorkerError("Worker deadline exceeded while writing")
            _, writable, _ = select.select([], [fd], [], min(remaining, 1))
            if writable:
                try: offset += os.write(fd, raw[offset:])
                except (BrokenPipeError, OSError) as exc: raise WorkerError("Worker input closed") from exc

    def message(self):
        while True:
            buffer = self.buffers["out"]
            if b"\n" in buffer:
                line, _, rest = buffer.partition(b"\n"); self.buffers["out"] = bytearray(rest)
                if not line or len(line) > self.profile["max_frame_bytes"]:
                    raise WorkerError("Invalid or oversized worker frame")
                value = loads(line)
                if not isinstance(value, dict): raise WorkerError("Worker protocol frame must be an object")
                return value
            remaining = self.deadline - time.monotonic()
            if remaining <= 0: raise WorkerError("Worker deadline exceeded")
            if not self.selector.get_map(): raise WorkerError("Worker exited before completion")
            for key, _ in self.selector.select(min(remaining, 1)):
                raw = os.read(key.fileobj.fileno(), 65536)
                if not raw:
                    self.selector.unregister(key.fileobj); continue
                self.output_bytes += len(raw)
                if self.output_bytes > self.profile["max_output_bytes"]:
                    raise WorkerError("Worker aggregate output exceeds bound")
                if key.data == "out":
                    self.buffers["out"].extend(raw)
                    if b"\n" not in self.buffers["out"] and len(self.buffers["out"]) > self.profile["max_frame_bytes"]:
                        raise WorkerError("Worker frame exceeds bound")
                # Stderr is counted, never retained: it may contain private model data.

    def request(self, method, params, on_event=None):
        self.identifier += 1; request_id = self.identifier
        self.send({"id": request_id, "method": method, "params": params})
        while True:
            message = self.message()
            if message.get("id") == request_id and "method" not in message:
                if "error" in message: raise WorkerError("App-server rejected " + method)
                if "result" not in message: raise WorkerError("App-server omitted response result")
                return message["result"]
            if on_event is not None:
                on_event(message)
            elif "id" in message:
                raise WorkerError("Unexpected app-server request before authorized turn")
            elif message.get("method") not in {"thread/started", "thread/status/changed", "account/updated",
                                                "account/rateLimits/updated", "model/verification", "remoteControl/status/changed"}:
                raise WorkerError("Unexpected app-server notification before authorized turn")

def _lookup(config, dotted):
    current = config
    for part in dotted.split("."):
        if not isinstance(current, dict) or part not in current: return None
        current = current[part]
    return current

def validate_config(result):
    config = result.get("config") if isinstance(result, dict) else None
    if not isinstance(config, dict): raise WorkerError("App-server did not expose effective configuration")
    for key, expected in CONFIG.items():
        actual = _lookup(config, key)
        if key == "permissions.worker_broker.filesystem" and isinstance(actual, dict):
            actual = {name: value for name, value in actual.items() if not (name == "glob_scan_max_depth" and value is None)}
        if actual != expected or (isinstance(expected, bool) and type(actual) is not bool):
            raise WorkerError("App-server effective capability differs from required profile: " + key)
    if not isinstance(config.get("hooks"), dict) or any(config["hooks"].values()):
        raise WorkerError("Worker hooks must be absent")

def validate_permissions(profiles):
    if not isinstance(profiles, dict) or not any(isinstance(row, dict) and row.get("id") == "worker_broker"
        and row.get("allowed") is True for row in profiles.get("data", [])):
        raise WorkerError("Managed requirements do not allow the isolated worker permission profile")


def validate_home(home):
    # app-server 0.153.4 does not implement exec's --ignore-user-config or
    # --ignore-rules. Require an owner-managed auth/session home with no code,
    # plugin, instruction or configuration ingress. Do not copy/read auth.json.
    home = Path(home)
    if not home.is_absolute() or home.is_symlink():
        raise WorkerError("Worker requires an absolute dedicated Codex home")
    for name in ("config.toml", "AGENTS.md", "AGENTS.override.md", "rules", "skills", "plugins", "hooks.json",
                 "requirements.toml", ".agents", ".codex"):
        if (home / name).exists() or (home / name).is_symlink():
            raise WorkerError("Worker Codex home contains unapproved configuration or executable capabilities: " + name)


class AppServerWorker:
    """One paid turn at a time; only completed phase-private histories are resumed.

    This trusts the reviewed official CLI and host account. It does not claim an
    arbitrary shell is safe in the authenticated process: no shell is provided.
    Product effects exist only in the caller's separately bounded source broker.
    """
    def __init__(self, profile, home, state_dir, *, argv=("codex",)):
        self.profile = validate_profile(profile); self.home = Path(home); self.state_dir = Path(state_dir)
        self.argv = list(argv); self._checked = None

    def preflight(self, *, require_smoke=True):
        validate_home(self.home)
        report = inspect_cli(self.argv, self.profile["codex_version"], self.profile["schema_sha256"])
        if require_smoke:
            path = Path(self.profile["smoke_attestation"])
            if not path.exists(): raise WorkerError("Target-host worker smoke is required before activation")
            smoke = read_record(path)
            if smoke.get("identity") != self.smoke_identity() or smoke.get("passed") is not True or smoke.get("model_called") is not True:
                raise WorkerError("Worker smoke does not match this reviewed runtime/profile")
        self._checked = report
        return report

    def smoke_identity(self):
        source = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path(__file__).parent.glob("*.py"))}
        return {"profile_hash": fingerprint(self.profile), "worker_source_hash": fingerprint(source),
                "codex_version": self.profile["codex_version"], "schema_sha256": self.profile["schema_sha256"]}

    def recover_completed(self, binding, prompt, output_schema, broker, run_id, model=""):
        """Read an exact completed local result without process, authentication or model I/O."""
        identity = {"binding": binding, "model": model, "profile": fingerprint(self.profile)}
        request_hash = fingerprint({"identity": identity, "prompt": prompt,
            "schema": output_schema, "tools": broker.tools, "run_id": run_id})
        record = self.state_dir / fingerprint(identity) / (fingerprint(run_id) + ".json")
        if not record.exists():
            return None
        prior = read_record(record)
        if prior.get("request_hash") != request_hash:
            raise WorkerError("Worker effect request changed during completed receipt recovery")
        return prior["receipt"] if prior.get("status") == "completed" else None

    def recover_bound(self, binding, run_id, model, external_identity):
        """Recover by the controller's already durable request hash, without rebuilding context."""
        identity = {"binding": binding, "model": model, "profile": fingerprint(self.profile)}
        record = self.state_dir / fingerprint(identity) / (fingerprint(run_id) + ".json")
        if not record.exists():
            return None
        prior = read_record(record)
        if prior.get("external_identity") != external_identity:
            raise WorkerError("Worker completed receipt differs from controller request identity")
        return prior["receipt"] if prior.get("status") == "completed" else None

    def execute(self, binding, prompt, output_schema, broker, run_id, model="", *, commissioning=False, external_identity=None):
        if self._checked is None: self.preflight(require_smoke=not commissioning)
        if not isinstance(binding, dict) or not binding or not isinstance(run_id, str) or not run_id:
            raise WorkerError("Worker requires controller-created authority and effect identities")
        identity = {"binding": binding, "model": model, "profile": fingerprint(self.profile)}
        session_key = fingerprint(identity); request_hash = fingerprint({"identity": identity, "prompt": prompt,
            "schema": output_schema, "tools": broker.tools, "run_id": run_id})
        root = self.state_dir / session_key; root.mkdir(parents=True, exist_ok=True, mode=0o700)
        import fcntl
        with (root / "lock").open("a") as guard:
            try: fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc: raise WorkerError("Another worker owns this session") from exc
            return self._execute(root, identity, request_hash, prompt, output_schema, broker, run_id, model, external_identity)

    def _execute(self, root, identity, request_hash, prompt, output_schema, broker, run_id, model, external_identity):
        record = root / (fingerprint(run_id) + ".json")
        if record.exists():
            prior = read_record(record)
            if prior.get("request_hash") != request_hash: raise WorkerError("Worker effect request changed")
            if prior.get("status") == "completed": return prior["receipt"]
            raise WorkerIndeterminate("Worker turn outcome is unknown; automatic replay is forbidden")
        session_file = root / "session.json"
        session = read_record(session_file) if session_file.exists() else None
        if session and session.get("identity") != identity: raise WorkerError("Worker session authority changed")
        # A new operation ID can only originate in the controller's durable reservation.
        # After owner-authorized retry of an uncertain operation, start a fresh thread.
        resume = bool(session and session.get("status") == "completed")
        baseline = session.get("usage_total", {}) if resume else {}
        with tempfile.TemporaryDirectory(prefix="worker-empty-") as directory:
            cwd = Path(directory)
            env = {key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL", "SSL_CERT_FILE", "SSL_CERT_DIR") if key in os.environ}
            env.update(HOME=str(cwd), CODEX_HOME=str(self.home), NO_COLOR="1")
            argv = self.argv + ["app-server", "--strict-config", "--stdio"]
            for key, value in CONFIG.items(): argv += ["-c", key + "=" + json_value(value)]
            connection = _Connection(argv, cwd, env, self.profile)
            dispatched = False
            try:
                connection.request("initialize", {"clientInfo": {"name": "controller_worker", "version": "1"},
                    "capabilities": {"experimentalApi": True}})
                connection.send({"method": "initialized", "params": {}})
                validate_config(connection.request("config/read", {"includeLayers": False}))
                profiles = connection.request("permissionProfile/list", {"cwd": str(cwd)})
                validate_permissions(profiles)
                params = {"cwd": str(cwd), "approvalPolicy": "never", "permissions": "worker_broker"}
                if not resume:
                    params["dynamicTools"] = broker.tools
                    params["environments"] = []
                    params["selectedCapabilityRoots"] = []
                if model: params["model"] = model
                if resume: params["threadId"] = session["thread_id"]
                started = connection.request("thread/resume" if resume else "thread/start", params)
                thread = started.get("thread", {}); thread_id = thread.get("id")
                if not isinstance(thread_id, str) or not thread_id or (resume and thread_id != session["thread_id"]):
                    raise WorkerError("App-server returned wrong thread identity")
                if started.get("instructionSources") not in (None, []):
                    raise WorkerError("Worker loaded unapproved instruction files")
                if (thread.get("status") or {}).get("type") == "active": raise WorkerError("Worker resumed an active thread")
                atomic(record, {"status": "dispatched", "request_hash": request_hash, "external_identity": external_identity, "thread_id": thread_id})
                atomic(session_file, {"identity": identity, "status": "dispatched", "thread_id": thread_id, "run_id": run_id})
                dispatched = True
                queued = []
                turn = connection.request("turn/start", {"threadId": thread_id,
                    "input": [{"type": "text", "text": prompt}], "approvalPolicy": "never",
                    "permissions": "worker_broker", "environments": [],
                    "outputSchema": output_schema}, queued.append)
                turn_id = turn.get("turn", {}).get("id")
                if not isinstance(turn_id, str) or not turn_id: raise WorkerError("App-server omitted turn identity")
                completed = False; final = None; usage_total = None; calls = {}; tool_bytes = 0
                while not completed:
                    message = queued.pop(0) if queued else connection.message()
                    method = message.get("method"); params = message.get("params", {})
                    if not isinstance(params, dict): raise WorkerError("Malformed worker notification")
                    if params.get("threadId", thread_id) != thread_id or params.get("turnId", turn_id) != turn_id:
                        raise WorkerError("Worker event belongs to another thread or turn")
                    if "id" in message:
                        if method != "item/tool/call": raise WorkerError("Unapproved worker server request")
                        if params.get("namespace") is not None:
                            raise WorkerError("Worker tool namespace is not authorized")
                        call_id = params.get("callId")
                        if not isinstance(call_id, str) or not call_id: raise WorkerError("Worker tool call has no identity")
                        name, arguments = params.get("tool"), params.get("arguments")
                        call_hash = fingerprint({"name": name, "arguments": arguments})
                        if call_id in calls:
                            if calls[call_id][0] != call_hash: raise WorkerError("Worker reused a tool identity with different arguments")
                            response = calls[call_id][1]
                        else:
                            if len(calls) >= self.profile["max_tool_calls"]: raise WorkerError("Worker tool operation bound reached")
                            try:
                                value = broker.call(name, arguments)
                                response = {"success": True, "contentItems": [{"type": "inputText", "text": canonical(value).decode()}]}
                            except ToolInputError as exc:
                                # Correctable argument mistakes remain inside this bounded turn.
                                # Authority, path, protocol and aggregate bounds stay fatal.
                                value = {"error": "invalid_tool_input", "message": str(exc)}
                                response = {"success": False, "contentItems": [{"type": "inputText", "text": canonical(value).decode()}]}
                            tool_bytes += len(canonical(response)) + len(canonical(arguments))
                            if tool_bytes > self.profile["max_tool_bytes"]: raise WorkerError("Worker cumulative tool byte bound reached")
                            calls[call_id] = (call_hash, response, name)
                        connection.send({"id": message["id"], "result": response})
                    elif method in {"item/started", "item/completed"}:
                        item = params.get("item", {}); kind = item.get("type")
                        if kind in FORBIDDEN_ITEMS or kind not in {"userMessage", "agentMessage", "reasoning", "plan", "dynamicToolCall", "contextCompaction"}:
                            raise WorkerError("Unexpected built-in tool or item in brokered worker")
                        if kind == "dynamicToolCall" and item.get("tool") not in {tool["name"] for tool in broker.tools}:
                            raise WorkerError("Unexpected dynamic worker tool")
                        if method == "item/completed" and kind == "agentMessage" and item.get("phase") in (None, "final_answer"):
                            final = item.get("text")
                    elif method == "thread/tokenUsage/updated":
                        usage_total = params.get("tokenUsage", {}).get("total")
                    elif method == "turn/completed":
                        ended = params.get("turn", {})
                        if ended.get("id") != turn_id or ended.get("status") != "completed" or ended.get("error"):
                            raise WorkerError("Worker turn did not complete successfully")
                        completed = True
                    elif method == "thread/started":
                        if params.get("thread", {}).get("id") != thread_id:
                            raise WorkerError("Worker started a different thread")
                    elif method in {"error", "turn/failed"}: raise WorkerError("App-server reported worker failure")
                    elif method not in {"turn/started", "thread/status/changed", "item/agentMessage/delta", "item/reasoning/textDelta",
                        "item/reasoning/summaryTextDelta", "item/reasoning/summaryPartAdded", "turn/plan/updated",
                        "account/rateLimits/updated", "model/rerouted", "serverRequest/resolved"}:
                        raise WorkerError("Unexpected worker protocol notification")
                if not isinstance(final, str): raise WorkerError("Worker omitted structured final output")
                result = broker.finalize(loads(final)); usage, total = usage_delta(usage_total, baseline)
                receipt = {"result": result, "usage": usage, "prompt_hash": fingerprint(prompt), "prompt_bytes": len(prompt.encode()), "worker": {"profile": self.profile["profile"],
                    "experimental": True, "thread_id": thread_id, "turn_id": turn_id, "session_binding": fingerprint(identity),
                    "tool_calls": len(calls), "tool_names": sorted({value[2] for value in calls.values()}),
                    "tool_bytes": tool_bytes, "resumed": resume}}
                atomic(record, {"status": "completed", "request_hash": request_hash, "external_identity": external_identity, "receipt": receipt})
                atomic(session_file, {"identity": identity, "status": "completed", "thread_id": thread_id,
                                      "run_id": run_id, "usage_total": total})
                return receipt
            except Exception as exc:
                if dispatched: raise WorkerIndeterminate("Worker stopped after dispatch; no automatic retry: " + run_id) from exc
                raise
            finally:
                connection.close()

def json_value(value):
    if isinstance(value, dict):
        return "{" + ",".join(canonical(key).decode() + "=" + json_value(child) for key, child in value.items()) + "}"
    return canonical(value).decode()

def usage_delta(current, previous):
    if current is None: return {}, {}
    if not isinstance(current, dict): raise WorkerError("Malformed worker usage")
    mapping = {"inputTokens": "input_tokens", "cachedInputTokens": "cached_input_tokens", "outputTokens": "output_tokens"}
    result = {}; total = {}
    for source, target in mapping.items():
        value = current.get(source, 0); old = previous.get(source, 0)
        if type(value) is not int or value < 0 or type(old) is not int or value < old:
            raise WorkerError("Worker usage regressed or is malformed")
        total[source] = value; result[target] = value - old
    if result["cached_input_tokens"] > result["input_tokens"]: raise WorkerError("Worker cached tokens exceed input")
    return result, total
