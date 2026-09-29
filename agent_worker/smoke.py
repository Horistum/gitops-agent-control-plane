"""Explicit target-host live commissioning; this command makes one paid model turn."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import uuid
from .broker import EDIT_SCHEMA, SourceBroker
from .protocol import WorkerError, atomic, exclusive_lock, fingerprint, read_record
from .transport import AppServerWorker


def run_smoke(profile, home, *, argv=("codex",), model="", retry_smoke=False, adapter_identity=None):
    directory = Path(profile["smoke_attestation"] + ".worker")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with exclusive_lock(directory / "commissioning.lock"):
        return _run_smoke(profile, home, argv=argv, model=model, retry_smoke=retry_smoke,
                          adapter_identity=adapter_identity)


def _run_smoke(profile, home, *, argv=("codex",), model="", retry_smoke=False, adapter_identity=None):
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
    worker = AppServerWorker(profile, home, directory, argv=argv, adapter_identity=adapter_identity)
    worker.preflight(require_smoke=False)
    identity = worker.smoke_identity(model)
    intent_path = directory / ("commissioning-" + fingerprint(model) + ".json")
    records = []
    if attestation_path.exists():
        prior = read_record(attestation_path)
        records = prior.get("attestations", [prior])
        if not isinstance(records, list): raise WorkerError("Malformed smoke attestation collection")
        for record in records:
            if not isinstance(record, dict): raise WorkerError("Malformed smoke attestation")
            if (not retry_smoke and record.get("identity") == identity
                    and record.get("passed") is True and record.get("model_called") is True):
                return record
    # Earlier runtime intents also fence a possibly dispatched commissioning.
    legacy_intent = directory / "commissioning.json"
    if legacy_intent.exists() and not retry_smoke:
        raise WorkerError("Legacy smoke intent requires review and explicit --retry-smoke")
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
            records = [row for row in records if row.get("identity", {}).get("model", "") != model]
            if records:
                atomic(attestation_path, {"schema": 2, "attestations": records})
            else:
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
                   "limitations": "Synthetic source-broker smoke bound to adapter authority code; does not execute adapter authorization, a product baseline, or establish protection against a compromised CLI/OS."}
    records = [row for row in records if row.get("identity", {}).get("model", "") != model]
    atomic(attestation_path, {"schema": 2, "attestations": records + [attestation]})
    atomic(intent_path, {**intent, "status": "completed"})
    return attestation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--adapter-module", required=True, help="Reviewed local adapter module exposing smoke_configuration(policy)")
    parser.add_argument("--model", help="One model from the adapter's configured model set")
    parser.add_argument("--retry-smoke", action="store_true", help="Explicitly authorize another potentially billed turn after reviewing prior outcome")
    args = parser.parse_args(); policy = read_record(Path(args.policy))
    import importlib
    configuration = importlib.import_module(args.adapter_module).smoke_configuration(policy)
    model = args.model if args.model is not None else configuration.pop("default_model")
    configuration.pop("default_model", None)
    if model not in configuration.pop("models"): raise WorkerError("Smoke model is outside the configured model set")
    result = run_smoke(**configuration, model=model, retry_smoke=args.retry_smoke)
    print(json.dumps({"passed": result["passed"], "model_called": True, "identity": result["identity"]}, indent=2))

if __name__ == "__main__":
    main()
