"""Controlled stdio peer, never an actual provider or evidence of live Codex."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tomllib

args = sys.argv[1:]
if "--version" in args:
    print("codex-cli fixture"); raise SystemExit
if "--help" in args:
    print("--strict-config --stdio --experimental --config app-server generate-json-schema"); raise SystemExit
if "generate-json-schema" in args:
    target = Path(args[args.index("--out") + 1]); target.mkdir()
    keys = ("dynamicTools", "inputSchema", "threadId", "turnId", "outputSchema", "approvalPolicy", "sandboxPolicy",
            "permissions", "experimentalApi", "contentItems")
    (target / "schema.json").write_text(json.dumps({"properties": {key: {} for key in keys}})); raise SystemExit
assert "app-server" in args and "--strict-config" in args and "--stdio" in args
assert not any(key in os.environ for key in ("GH_TOKEN", "GITHUB_TOKEN", "OPENAI_API_KEY", "SSH_AUTH_SOCK"))
assert Path.cwd() == Path(os.environ["HOME"])
scenario = args[args.index("--scenario") + 1] if "--scenario" in args else "normal"
config = {}
for index, value in enumerate(args):
    if value != "-c": continue
    key, raw = args[index + 1].split("=", 1); current = config
    for part in key.split(".")[:-1]: current = current.setdefault(part, {})
    current[key.split(".")[-1]] = tomllib.loads("value=" + raw)["value"]
if scenario == "bad-config": config["features"]["apps"] = True
home = Path(os.environ["CODEX_HOME"]); home.mkdir(parents=True, exist_ok=True)
state_path = home / "fixture-state.json"
state = json.loads(state_path.read_text()) if state_path.exists() else {"threads": 0, "turns": 0, "totals": {}}

def send(value):
    print(json.dumps(value), flush=True)

def answer(request, value):
    send({"id": request["id"], "result": value})

def event(method, params, **metadata):
    send({"method": method, "params": params, **metadata})

def blank(schema, name=""):
    if "enum" in schema:
        return "ready" if name == "verdict" else schema["enum"][0]
    if "const" in schema: return schema["const"]
    kind = schema.get("type")
    if kind == "object": return {key: blank(value, key) for key, value in schema["properties"].items()}
    if kind == "array": return []
    if kind == "boolean": return False
    if kind == "integer": return 0
    return "fixture" if name == "summary" else ""

for line in sys.stdin:
    request = json.loads(line); method = request.get("method"); params = request.get("params", {})
    if method == "initialize": answer(request, {"userAgent": "controlled-fixture"})
    elif method == "initialized": pass
    elif method == "config/read":
        if scenario == "startup-notices-after-config": answer(request, {"config": config})
        if scenario in {"startup-notices", "startup-notices-after-config"}:
            event("warning", {"message": "Informational startup warning", "threadId": None}, emittedAtMs=1790648857904)
            event("deprecationNotice", {"summary": "Informational deprecation", "details": None})
            event("configWarning", {"summary": "Informational config warning", "details": "Fixture detail",
                "path": "/fixture/config.toml", "range": {"start": {"line": 1, "column": 1}, "end": {"line": 1, "column": 2}}}, emittedAtMs=1790648857905)
        elif scenario == "startup-bad-notice": event("warning", {"message": {"private": "never log notice parameters"}})
        elif scenario == "startup-bad-timestamp": event("configWarning", {"summary": "Bad timestamp"}, emittedAtMs=True)
        elif scenario == "startup-bad-range": event("configWarning", {"summary": "Bad range", "range": {"start": {"line": True, "column": 1}, "end": {"line": 2, "column": 1}}})
        elif scenario == "startup-notice-action": event("deprecationNotice", {"summary": "Ignored action", "action": "execute"})
        elif scenario == "startup-notice-request": send({"id": 90, "method": "warning", "params": {"message": "Reply required"}})
        elif scenario == "startup-forbidden": event("item/started", {"item": {"type": "commandExecution"}})
        elif scenario == "startup-unknown": event("unknown/private\nnotice", {"private": "never log notice parameters"})
        if scenario != "startup-notices-after-config": answer(request, {"config": config})
    elif method == "permissionProfile/list": answer(request, {"data": [{"id": "worker_broker", "allowed": True}], "nextCursor": None})
    elif method in ("thread/start", "thread/resume"):
        if method == "thread/start":
            state["threads"] += 1; thread_id = "thread-" + str(state["threads"])
        else: thread_id = params["threadId"]
        if method == "thread/start":
            tools = {tool["name"] for tool in params["dynamicTools"]}
            state.setdefault("tools", {})[thread_id] = list(tools)
        else: tools = set(state["tools"][thread_id])
        answer(request, {"thread": {"id": thread_id, "ephemeral": False}, "instructionSources": []})
    elif method == "turn/start":
        assert params["permissions"] == "worker_broker"
        assert params["environments"] == []
        assert params["approvalPolicy"] == "never"
        state["turns"] += 1; turn_id = "turn-" + str(state["turns"])
        state_path.write_text(json.dumps(state))
        answer(request, {"turn": {"id": turn_id, "status": "inProgress"}})
        if scenario == "crash": raise SystemExit(8)
        if scenario == "malformed": print('{"method":"a","method":"b"}', flush=True); continue
        event("turn/started", {"threadId": thread_id, "turn": {"id": turn_id, "status": "inProgress"}})
        if scenario == "forbidden-item":
            event("item/started", {"threadId": thread_id, "turnId": turn_id, "item": {"id": "bad", "type": "commandExecution"}})
            continue
        if scenario == "forbidden-request":
            send({"id": 90, "method": "item/commandExecution/requestApproval", "params": {"threadId": thread_id, "turnId": turn_id}})
            continue
        def call(name, arguments, call_id):
            params = {"threadId": "alien" if scenario == "wrong-thread" else thread_id,
                      "turnId": turn_id, "callId": call_id, "tool": name, "arguments": arguments}
            send({"id": 100 + len(call_id), "method": "item/tool/call", "params": params})
            response = json.loads(sys.stdin.readline())
            return json.loads(response["result"]["contentItems"][0]["text"])
        smoke = "Commission the source broker" in params["input"][0]["text"]
        source_path = "smoke.py" if smoke else (args[args.index("--source-path") + 1] if "--source-path" in args else "src/service.py")
        call("search_source", {"literal": "answer" if smoke else "value"}, "search")
        if scenario == "corrected-input":
            failed = call("read_source", {"path": source_path, "start_line": 20, "end_line": 1}, "invalid-read")
            assert failed["error"] == "invalid_tool_input"
        source = call("read_source", {"path": source_path, "start_line": 1, "end_line": 20}, "read")
        if scenario in ("duplicate", "changed-duplicate"):
            call("read_source", {"path": source_path, "start_line": 1,
                 "end_line": 19 if scenario == "changed-duplicate" else 20}, "read")
        if "stage_edits" in tools and scenario not in {"direct-edits", "direct-nul"}:
            if scenario == "corrected-input":
                failed = call("stage_edits", {"edits": [{"path": source_path, "expected_sha256": "stale",
                    "delete": False, "content": "value = 2\n"}]}, "stale-edit")
                assert failed["error"] == "invalid_tool_input"
            changed = call("stage_edits", {"edits": [{"path": source_path, "expected_sha256": source["sha256"],
                "delete": False, "content": "def answer():\n    return 2\n" if smoke else "value = 2\n"}]}, "edit1")
            if not smoke: call("stage_edits", {"edits": [{"path": source_path, "expected_sha256": changed["staged"][0]["sha256"],
                "delete": False, "content": "value = 3\n"}]}, "edit2")
        total = state["totals"].setdefault(thread_id, {"inputTokens": 0, "cachedInputTokens": 0, "outputTokens": 0})
        total["inputTokens"] += 10; total["outputTokens"] += 3
        event("thread/tokenUsage/updated", {"threadId": thread_id, "turnId": turn_id, "tokenUsage": {"total": total}})
        result = blank(params["outputSchema"])
        if scenario in {"direct-edits", "direct-nul"}:
            result["edits"] = [{"path": source_path, "expected_sha256": source["sha256"],
                "delete": False, "content": "value = 3\n" + ("\0" if scenario == "direct-nul" else "")}]
        event("item/completed", {"threadId": thread_id, "turnId": turn_id,
            "item": {"id": "final", "type": "agentMessage", "phase": "final_answer", "text": json.dumps(result)}})
        state_path.write_text(json.dumps(state))
        event("turn/completed", {"threadId": thread_id, "turn": {"id": turn_id, "status": "completed", "error": None}})
