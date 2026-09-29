"""Offline inspection of the exact installed official CLI, without model or auth calls."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import selectors
import signal
import time
from .protocol import WorkerError, fingerprint, loads

# Disabling a tool in a prompt is not enforcement. Every key is checked again
# through config/read before a turn. A reviewed version/schema pin is mandatory.
DISABLED_FEATURES = ("shell_tool", "unified_exec", "multi_agent", "apps", "goals", "hooks", "memories",
                     "remote_plugin", "skill_mcp_dependency_install", "plugins", "browser_use", "browser_use_external",
                     "browser_use_full_cdp_access", "computer_use", "image_generation", "shell_snapshot",
                     "code_mode_host", "workspace_dependencies", "skill_search", "tool_suggest", "view_image")

def _run(argv, *, cwd, env, limit=2_000_000, timeout=60):
    """Bound aggregate output while the process runs, including stderr."""
    try:
        proc = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    except OSError as exc:
        raise WorkerError("Codex capability command unavailable") from exc
    output = bytearray(); total = 0; deadline = time.monotonic() + timeout
    try:
        with selectors.DefaultSelector() as selector:
            for stream in (proc.stdout, proc.stderr):
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0: raise WorkerError("Codex capability command timed out")
                for key, _ in selector.select(min(remaining, 0.1)):
                    raw = os.read(key.fileobj.fileno(), min(65536, limit - total + 1))
                    if not raw:
                        selector.unregister(key.fileobj); continue
                    total += len(raw)
                    if total > limit: raise WorkerError("Codex capability output exceeded bound")
                    if key.fileobj is proc.stdout: output.extend(raw)
            try: proc.wait(timeout=max(0.001, deadline - time.monotonic()))
            except subprocess.TimeoutExpired as exc: raise WorkerError("Codex capability command timed out") from exc
        if proc.returncode: raise WorkerError("Codex capability command failed")
        return bytes(output)
    finally:
        # Kill the group even if its leader exited with a descendant holding a pipe.
        try: os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError: pass
        try: proc.wait(timeout=0.5)
        except subprocess.TimeoutExpired: pass
        try: os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError: pass
        proc.wait()
        proc.stdout.close(); proc.stderr.close()

def inspect_cli(argv=("codex",), expected_version=None, expected_schema=None):
    with tempfile.TemporaryDirectory(prefix="worker-capabilities-") as directory:
        root = Path(directory)
        env = {key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL") if key in os.environ}
        env.update(HOME=str(root), CODEX_HOME=str(root / "home"), NO_COLOR="1")
        version = _run(list(argv) + ["--version"], cwd=root, env=env).decode().strip()
        if expected_version is not None and version != expected_version:
            raise WorkerError("Installed Codex worker version differs from policy")
        help_text = _run(list(argv) + ["--help"], cwd=root, env=env).decode()
        app_help = _run(list(argv) + ["app-server", "--help"], cwd=root, env=env).decode()
        for flag in ("--strict-config", "--stdio"):
            if flag not in app_help:
                raise WorkerError("Official app-server does not advertise required capability: " + flag)
        if "generate-json-schema" not in app_help:
            raise WorkerError("Official CLI lacks app-server schema generation")
        schema_help = _run(list(argv) + ["app-server", "generate-json-schema", "--help"], cwd=root, env=env).decode()
        if "--experimental" not in schema_help:
            raise WorkerError("App-server cannot expose the experimental dynamic-tool schema")
        output = root / "schemas"
        _run(list(argv) + ["app-server", "generate-json-schema", "--experimental", "--out", str(output)], cwd=root, env=env)
        records = {}; properties = set(); total = 0
        def visit(value):
            if isinstance(value, dict):
                properties.update(value.get("properties", {}))
                for child in value.values(): visit(child)
            elif isinstance(value, list):
                for child in value: visit(child)
        for path in sorted(output.rglob("*")):
            if path.is_symlink(): raise WorkerError("Generated schema contains symlink")
            if not path.is_file(): continue
            total += path.stat().st_size
            if total > 30_000_000 or len(records) >= 2000:
                raise WorkerError("Generated schema exceeds bound")
            raw = path.read_bytes()
            records[path.relative_to(output).as_posix()] = hashlib.sha256(raw).hexdigest()
            if path.suffix == ".json": visit(loads(raw))
        required = {"dynamicTools", "inputSchema", "threadId", "turnId", "outputSchema", "approvalPolicy",
                    "sandboxPolicy", "permissions", "experimentalApi", "contentItems"}
        if not records or not required <= properties:
            raise WorkerError("Generated schema lacks required brokered worker capabilities: " + ", ".join(sorted(required - properties)))
        schema_hash = fingerprint(records)
        if expected_schema is not None and schema_hash != expected_schema:
            raise WorkerError("Installed Codex app-server schema differs from reviewed pin")
        from .transport import CONFIG, _Connection, json_value, validate_config, validate_permissions
        probe_argv = list(argv) + ["app-server", "--strict-config", "--stdio"]
        for key, value in CONFIG.items():
            probe_argv += ["-c", key + "=" + json_value(value)]
        Path(env["CODEX_HOME"]).mkdir(exist_ok=True)
        connection = _Connection(probe_argv, root, env,
            {"timeout_seconds": 20, "max_frame_bytes": 1_000_000, "max_output_bytes": 2_000_000})
        try:
            connection.request("initialize", {"clientInfo": {"name": "worker_capability", "version": "1"},
                "capabilities": {"experimentalApi": True}})
            connection.send({"method": "initialized", "params": {}})
            validate_config(connection.request("config/read", {"includeLayers": False}))
            validate_permissions(connection.request("permissionProfile/list", {"cwd": str(root)}))
        finally:
            connection.close()
        return {"runtime_configuration": "verified", "permission_profile": "verified",
                "profile": "codex-app-server-broker/v1", "codex_version": version,
                "schema_sha256": schema_hash, "schema_files": len(records), "model_called": False,
                "authentication": "not-accessed", "experimental": True}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex", default="codex")
    parser.add_argument("--expected-version")
    parser.add_argument("--expected-schema-sha256")
    args = parser.parse_args()
    print(json.dumps(inspect_cli([args.codex], args.expected_version, args.expected_schema_sha256), indent=2))

if __name__ == "__main__":
    main()
