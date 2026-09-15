"""Portable, typed verification decisions. Observations must come from an adapter.

No command execution, imported product code, eval, model verdicts or provider I/O.
"""
from __future__ import annotations

import json
import hashlib
from .decisions import CoreError, _ids, _sha

EVIDENCE_CONTRACT = "verification-evidence/v1"


def validate_goal_conditions(conditions, items, case_ids):
    if not isinstance(conditions, list) or len(conditions) > 256:
        raise CoreError("Goal conditions must be a bounded typed list")
    _ids([r.get("id") if isinstance(r, dict) else None for r in conditions], "goal condition ids")
    for row in conditions:
        if row.get("kind") == "cli_case" and set(row) == {"id", "kind", "case"}:
            if row["case"] not in case_ids: raise CoreError("Goal names an unapproved CLI case")
        elif row.get("kind") == "criterion" and set(row) == {"id", "kind", "item", "criterion"}:
            if row["item"] not in items: raise CoreError("Goal condition exceeds item scope")
            _ids([row["criterion"]], "criterion")
        else:
            raise CoreError("Unsupported goal condition; arbitrary expressions are forbidden")
    return conditions


def evaluate_goal_conditions(conditions, observations):
    rows = []
    for condition in conditions:
        if condition["kind"] == "cli_case":
            value = observations.get("cli_cases", {}).get(condition["case"])
        else:
            value = observations.get("criteria", {}).get(condition["item"], {}).get(condition["criterion"])
        rows.append({"id": condition["id"], "passed": value is True})
    return {"contract": EVIDENCE_CONTRACT, "conditions_hash": identity(conditions),
            "passed": all(r["passed"] for r in rows), "rows": rows}


def identity(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def validate_bindings(criteria, bindings) -> list[dict]:
    expected = set(_ids(criteria, "criteria", nonempty=True))
    if not isinstance(bindings, list) or not 1 <= len(bindings) <= 256:
        raise CoreError("Explicit bounded acceptance/test bindings are required")
    pairs, modes = set(), {}
    for row in bindings:
        if not isinstance(row, dict) or set(row) != {"criterion_id", "test_id", "mode"}:
            raise CoreError("Malformed acceptance/test binding")
        test = row["test_id"]
        if row["criterion_id"] not in expected or not isinstance(test, str) or not 1 <= len(test) <= 500:
            raise CoreError("Unknown criterion or invalid test identity")
        if row["mode"] not in {"new_behavior", "regression"}:
            raise CoreError("Unknown test binding semantics")
        pair = (row["criterion_id"], test)
        if pair in pairs or (test in modes and modes[test] != row["mode"]):
            raise CoreError("Ambiguous acceptance/test binding")
        pairs.add(pair); modes[test] = row["mode"]
    if {r["criterion_id"] for r in bindings} != expected:
        raise CoreError("Every criterion needs executable evidence")
    return bindings


def test_failure_kind(receipt: dict) -> str:
    junit = receipt.get("junit", {})
    if junit.get("failed_identities") or junit.get("assertion_failures", 0):
        return "product"
    if junit.get("error_identities") or junit.get("errors", 0):
        return "ambiguous"
    if not junit.get("executed_identities", junit.get("identities", [])):
        return "test_preparation"
    return "ambiguous"


def acceptance_evidence(criteria, bindings, baseline: dict, candidate: dict) -> dict:
    """Each new-behavior test must fail on base and pass on the final candidate.

Regression bindings must pass on both. A compile error or an absent/skipped test
cannot serve as a negative control. These are test observations, not a proof that
the build producing JUnit is trusted; the external CLI profile supplies that gate.
"""
    validate_bindings(criteria, bindings)
    for receipt in (baseline, candidate):
        _sha(receipt.get("head")); _sha(receipt.get("base"))
    if baseline["base"] != candidate["base"] or baseline.get("spec_hash") != candidate.get("spec_hash"):
        raise CoreError("Counterfactual evidence has a different base or specification")
    old, new = baseline.get("junit", {}), candidate.get("junit", {})
    old_run, new_run = set(old.get("executed_identities", [])), set(new.get("executed_identities", []))
    old_bad, new_bad = set(old.get("failed_identities", [])), set(new.get("failed_identities", []))
    old_errors, new_errors = set(old.get("error_identities", [])), set(new.get("error_identities", []))
    rows = []
    for row in bindings:
        test = row["test_id"]
        negative = test in old_bad if row["mode"] == "new_behavior" else test not in old_bad
        passed = (candidate.get("passed") is True and test in old_run and test in new_run
                  and test not in old_errors | new_errors | new_bad and negative)
        rows.append({**row, "passed": passed, "baseline_head": baseline["head"],
                     "candidate_head": candidate["head"]})
    # A broken preexisting test or broken test harness is never a valid negative control.
    permitted_failures = {r["test_id"] for r in bindings if r["mode"] == "new_behavior"}
    complete = bool(rows) and not old_errors and old_bad <= permitted_failures and all(r["passed"] for r in rows)
    return {"contract": EVIDENCE_CONTRACT, "passed": complete, "rows": rows,
            "baseline_receipt_hash": identity(baseline), "candidate_receipt_hash": identity(candidate)}


def _pointer(document, pointer: str):
    if pointer == "":
        return document
    if not isinstance(pointer, str) or not pointer.startswith("/") or len(pointer) > 1000:
        raise CoreError("Expected a bounded JSON pointer")
    for raw in pointer[1:].split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(document, dict):
            document = document[token]
        elif isinstance(document, list) and token.isdigit():
            document = document[int(token)]
        else:
            raise KeyError(token)
    return document


def validate_predicates(predicates) -> list[dict]:
    if not isinstance(predicates, list) or not 1 <= len(predicates) <= 256:
        raise CoreError("Typed success predicates must be a nonempty bounded list")
    _ids([p.get("id") if isinstance(p, dict) else None for p in predicates], "predicate ids")
    for p in predicates:
        op = p.get("op")
        keys = {"id", "op", "expected"} | ({"pointer"} if op == "json_equals" else set())
        if set(p) != keys or op not in {"exit_code", "stdout_equals", "stdout_contains", "json_equals"}:
            raise CoreError("Unsupported typed success predicate")
        if op == "exit_code" and (type(p["expected"]) is not int or not -255 <= p["expected"] <= 255):
            raise CoreError("Invalid expected exit code")
        if op.startswith("stdout_") and (not isinstance(p["expected"], str) or not p["expected"]):
            raise CoreError("Expected output must be explicit nonempty text")
        if op == "json_equals" and (not isinstance(p["pointer"], str) or
                                    (p["pointer"] and not p["pointer"].startswith("/"))):
            raise CoreError("Invalid JSON pointer")
        if len(json.dumps(p, allow_nan=False).encode()) > 100_000:
            raise CoreError("Predicate exceeds byte budget")
    return predicates


def evaluate_predicates(predicates, observation: dict) -> dict:
    validate_predicates(predicates)
    stdout = observation.get("stdout")
    if not isinstance(stdout, str) or len(stdout.encode()) > 2_000_000 or type(observation.get("exit_code")) is not int:
        raise CoreError("Malformed external process observation")
    rows = []
    for p in predicates:
        try:
            if p["op"] == "exit_code":
                passed = observation["exit_code"] == p["expected"]
            elif p["op"] == "stdout_equals":
                passed = stdout == p["expected"]
            elif p["op"] == "stdout_contains":
                passed = p["expected"] in stdout
            else:
                def unique(pairs):
                    result = {}
                    for k, v in pairs:
                        if k in result: raise ValueError("Duplicate JSON key")
                        result[k] = v
                    return result
                document = json.loads(stdout, object_pairs_hook=unique,
                                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))
                passed = identity(_pointer(document, p["pointer"])) == identity(p["expected"])
        except (ValueError, KeyError, IndexError, TypeError, RecursionError):
            passed = False
        rows.append({"id": p["id"], "passed": bool(passed)})
    return {"contract": EVIDENCE_CONTRACT, "passed": all(r["passed"] for r in rows),
            "predicates_hash": identity(predicates), "observation_hash": identity(observation), "rows": rows}
