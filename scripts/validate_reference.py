#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRODUCT = ROOT / "examples" / "minimal-product"


def check(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit("reference validation failed: " + message)


def run(argv: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess:
    completed = subprocess.run(argv, cwd=cwd, text=True, capture_output=True)
    if completed.returncode:
        raise SystemExit(
            "reference validation failed: command failed: "
            + " ".join(argv)
            + "\nSTDOUT:\n"
            + completed.stdout[-4000:]
            + "\nSTDERR:\n"
            + completed.stderr[-4000:]
        )
    return completed


def validate_publication_identity() -> None:
    for name in ("LICENSE", "NOTICE", "TRADEMARKS.md", "CONTRIBUTING.md", "SUPPORT.md", ".github/SECURITY.md", "docs/RELEASES.md"):
        check((ROOT / name).is_file(), f"publication file missing: {name}")
    check("Apache License" in (ROOT / "LICENSE").read_text(), "LICENSE is not Apache-2.0")
    notice = (ROOT / "NOTICE").read_text()
    check(re.search(r"Copyright\s+\d{4}(?:-\d{4})?\s+Horistum contributors", notice) is not None, "NOTICE copyright/provenance format drift")


def validate_schemas_and_static_contracts() -> None:
    from reference_runtime.schema_validation import load_schema, validate_json_file
    from reference_runtime.contracts import validate_goal, validate_policy
    from reference_runtime.base import BaseEngine

    schema_files = sorted((ROOT / "schemas").glob("*.schema.json"))
    check(bool(schema_files), "no JSON Schemas found")
    for path in schema_files:
        load_schema(path)

    validate_json_file(ROOT / "examples" / "goal.example.json", ROOT / "schemas" / "goal.schema.json")
    validate_json_file(ROOT / "config" / "reference-policy.json", ROOT / "schemas" / "policy.schema.json")
    validate_json_file(
        PRODUCT / ".agent-control" / "verification-probes.json",
        ROOT / "schemas" / "verification-probes.schema.json",
    )
    goal = json.loads((ROOT / "examples" / "goal.example.json").read_text())
    policy = json.loads((ROOT / "config" / "reference-policy.json").read_text())
    validate_goal(goal)
    validate_policy(policy)
    check(policy["reference_contract"] == "gitops-agent-control-plane/v5", "contract version drift")

    scenario_schema = ROOT / "schemas" / "scenario.schema.json"
    scenarios = sorted((ROOT / "examples" / "scenarios").glob("*.json"))
    required_scenarios = {
        "insufficient-tests", "assertion-tamper", "junit-forgery", "nonce-forgery",
        "probe-aware", "crash-recovery", "happy-path",
    }
    check(required_scenarios <= {path.stem for path in scenarios}, "critical conformance scenarios missing")
    for path in scenarios:
        validate_json_file(path, scenario_schema)
        value = json.loads(path.read_text())
        check(value["name"] == path.stem, f"scenario identity drift: {path.name}")

    probes = json.loads((PRODUCT / ".agent-control" / "verification-probes.json").read_text())
    check(probes.get("schema") == 2 and probes.get("baseline") and probes.get("acceptance"), "verification probes missing")
    probe_ids = [probe.get("id") for probe in probes["baseline"] + probes["acceptance"]]
    check(all(isinstance(x, str) and x for x in probe_ids) and len(probe_ids) == len(set(probe_ids)), "verification probe ids invalid")
    for probe in probes["baseline"] + probes["acceptance"]:
        BaseEngine._validate_probe(probe)
        check("args" not in probe and "expect" not in probe, "fixed public probe input/expectation returned")


def validate_product_baseline_without_mutation() -> None:
    before = {path.relative_to(PRODUCT).as_posix(): path.read_bytes() for path in PRODUCT.rglob("*") if path.is_file()}
    with tempfile.TemporaryDirectory(prefix="reference-baseline-") as directory:
        copy = Path(directory) / "product"
        shutil.copytree(PRODUCT, copy)
        run([sys.executable, "-S", "ci/run_tests.py"], cwd=copy)
        junit = copy / "build" / "test-results" / "reference" / "TEST-reference.xml"
        check(junit.is_file(), "baseline JUnit missing")
        tests = list(ET.parse(junit).getroot().iter("testcase"))
        check(len(tests) == 3, f"expected 3 baseline tests, observed {len(tests)}")
    after = {path.relative_to(PRODUCT).as_posix(): path.read_bytes() for path in PRODUCT.rglob("*") if path.is_file()}
    check(before == after, "validator mutated source example")


def validate_authority_layout() -> None:
    from reference_runtime.contracts import digest_paths, matches_any

    policy = json.loads((ROOT / "config" / "reference-policy.json").read_text())
    snapshot = digest_paths(PRODUCT, policy["authority_paths"])
    check(bool(snapshot["files"]), "authority snapshot would be empty")
    check(".agent-control/verification-probes.json" in snapshot["files"], "verification probes are not owner-controlled source authority")
    for pattern in policy["authority_paths"]:
        check(any(matches_any(path, [pattern]) for path in snapshot["files"]), f"authority pattern matched no files: {pattern}")


def validate_python_and_shell() -> None:
    for base in (ROOT / "reference_runtime", ROOT / "scripts", ROOT / "tests", PRODUCT / "src", PRODUCT / "tests", PRODUCT / "ci"):
        for path in base.rglob("*.py"):
            ast.parse(path.read_text(), filename=str(path))
    for path in (ROOT / "scripts").glob("*.sh"):
        run(["bash", "-n", str(path)])
    run(["bash", "-n", str(ROOT / "scripts" / "agentctl")])
    run(["bash", str(ROOT / "scripts" / "bootstrap-linux.sh"), "self-test"])


def validate_docs_claims() -> None:
    readme = (ROOT / "README.md").read_text().lower()
    security = (ROOT / "docs" / "SECURITY.md").read_text().lower()
    architecture = (ROOT / "docs" / "ARCHITECTURE.md").read_text().lower()
    verification = (ROOT / "docs" / "VERIFICATION.md").read_text().lower()
    check("gitops-agent-control-plane/v5" in verification, "verification docs do not name contract v5")
    check("not a security sandbox" in readme, "README must disclose local executor boundary")
    check("not authoritative" in security and "junit" in security, "SECURITY must disclose diagnostic JUnit trust boundary")
    check("hmac" in security and "control fd" in security, "SECURITY must describe private receipt challenge channel")
    check("random" in verification and "invariant" in verification, "VERIFICATION must describe runtime-generated invariant cases")
    check("cannot guarantee adversarial evidence integrity" in architecture, "ARCHITECTURE must not overclaim execution evidence")
    check("not an authenticity mechanism" in security and "anchor" in security, "SECURITY must disclose event-chain authenticity boundary")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fast", action="store_true")
    args = parser.parse_args(argv)
    validate_publication_identity()
    validate_schemas_and_static_contracts()
    validate_authority_layout()
    validate_python_and_shell()
    validate_docs_claims()
    if not args.fast:
        validate_product_baseline_without_mutation()
    print(json.dumps({
        "passed": True,
        "reference_contract": "gitops-agent-control-plane/v5",
        "licensed": "Apache-2.0",
        "provenance": "Horistum",
        "baseline_tests": 0 if args.fast else 3,
        "source_tree_mutated": False,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
