"""Explicit target-host live commissioning; this command makes one paid model turn."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import uuid
from .broker import EDIT_SCHEMA, SourceBroker
from .protocol import WorkerError, atomic, read_record
from .transport import AppServerWorker


def run_smoke(profile, home, *, argv=("codex",), model="", retry_smoke=False):
    import fcntl
    directory = Path(profile["smoke_attestation"] + ".worker")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (directory / "commissioning.lock").open("a") as guard:
        try:
            fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise WorkerError("Another commissioning process owns the worker smoke") from exc
        return _run_smoke(profile, home, argv=argv, model=model, retry_smoke=retry_smoke)


def _run_smoke(profile, home, *, argv=("codex",), model="", retry_smoke=False):
    original = "def answer():\n    return 1\n"; replacement = "def answer():\n    return 2\n"
    observed = []
    def read(path):
        if path != "smoke.py": return {"missing": True}
        return {"text": original, "sha256": hashlib.sha256(original.encode()).hexdigest()}
    def authorize(edits):
        if len(edits) != 1 or edits[0]["path"] != "smoke.py" or edits[0]["content"] != replacement or edits[0]["delete"]:
            raise WorkerError("Live smoke proposed an unexpected edit")
    broker = SourceBroker(read, lambda literal: {"paths": ["smoke.py"] if literal in original else []}, authorize, writable=True)
    original_call = broker.call
    def call(name, arguments):
        value = original_call(name, arguments); observed.append(name); return value
    broker.call = call
    schema = {"type": "object", "additionalProperties": False,
        "properties": {"verdict": {"type": "string", "enum": ["ready"]},
                       "edits": {"type": "array", "items": EDIT_SCHEMA}}, "required": ["verdict", "edits"]}
    # Commissioning is itself a potentially billed effect. Its intent and worker
    # journal survive process crashes; rerunning never silently repeats a turn.
    attestation_path = Path(profile["smoke_attestation"])
    directory = attestation_path.parent / (attestation_path.name + ".worker")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    worker = AppServerWorker(profile, home, directory, argv=argv)
    worker.preflight(require_smoke=False)
    identity = worker.smoke_identity()
    intent_path = directory / "commissioning.json"
    if attestation_path.exists() and not retry_smoke:
        prior = read_record(attestation_path)
        if prior.get("identity") == identity and prior.get("passed") is True and prior.get("model_called") is True:
            return prior
    previous = read_record(intent_path) if intent_path.exists() else None
    if previous and not retry_smoke:
        if previous["identity"] != identity:
            raise WorkerError("Unfinished smoke belongs to another profile/runtime; explicit --retry-smoke is required")
        intent = previous
    else:
        intent = {"identity": identity, "operation": uuid.uuid4().hex, "status": "reserved"}
        if previous:
            atomic(directory / ("retired-" + previous["operation"] + ".json"), previous)
        if attestation_path.exists():
            # An explicitly retried uncertain commissioning must not leave an
            # older successful attestation eligible for activation.
            archived = read_record(attestation_path)
            atomic(directory / ("attestation-before-" + intent["operation"] + ".json"), archived)
            attestation_path.unlink()
            import os
            parent_fd = os.open(attestation_path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try: os.fsync(parent_fd)
            finally: os.close(parent_fd)
        atomic(intent_path, intent)
    value = worker.execute({"commissioning": intent["operation"]},
        "Commission the source broker using only its three tools. First search for the literal answer, "
        "then read smoke.py lines 1 through 10, then stage its exact replacement as " + repr(replacement) +
        ". Do not invoke any other tool. Return ready with edits=[] after staging. This is synthetic smoke source, not product work.",
        schema, broker, "target-smoke-" + intent["operation"], model, commissioning=True)
    if set(value["worker"]["tool_names"]) != {tool["name"] for tool in broker.tools} or value["result"].get("verdict") != "ready":
        raise WorkerError("Live smoke did not exercise every broker capability")
    authorize(value["result"].get("edits", []))
    attestation = {"identity": identity, "passed": True, "model_called": True,
                   "experimental": True, "observed_tools": value["worker"]["tool_names"], "usage": value["usage"],
                   "operation": intent["operation"],
                   "limitations": "Synthetic broker smoke; not a product baseline or protection against a compromised CLI/OS."}
    atomic(attestation_path, attestation)
    atomic(intent_path, {**intent, "status": "completed"})
    return attestation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--adapter", required=True, choices=("flow", "reference"))
    parser.add_argument("--retry-smoke", action="store_true", help="Explicitly authorize another potentially billed turn after reviewing prior outcome")
    args = parser.parse_args(); policy = read_record(Path(args.policy))
    if args.adapter == "flow":
        profile, home, argv = policy["agent_worker"], policy["codex_home"], ["codex"]
        model = policy.get("models", {}).get("default", "")
    else:
        config = policy["reasoning"]; profile, home, argv = config["worker"], config["codex_home"], config["argv"]
        model = config["model"]
    result = run_smoke(profile, home, argv=argv, model=model, retry_smoke=args.retry_smoke)
    print(json.dumps({"passed": result["passed"], "model_called": True, "identity": result["identity"]}, indent=2))

if __name__ == "__main__":
    main()
