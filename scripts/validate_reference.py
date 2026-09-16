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
sys.path.insert(0, str(ROOT))
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
    for name in (
        "LICENSE", "NOTICE", "TRADEMARKS.md", "CONTRIBUTING.md", "SUPPORT.md",
        ".github/SECURITY.md", "docs/RELEASES.md",
    ):
        check((ROOT / name).is_file(), f"publication file missing: {name}")
    check("Apache License" in (ROOT / "LICENSE").read_text(), "LICENSE is not Apache-2.0")
    notice = (ROOT / "NOTICE").read_text()
    check(
        re.search(r"Copyright\s+\d{4}(?:-\d{4})?\s+Horistum contributors", notice) is not None,
        "NOTICE copyright/provenance format drift",
    )


def validate_schemas_and_static_contracts() -> None:
    run([sys.executable, str(ROOT / "scripts" / "generate_runtime_schemas.py"), "--check"])
    run([sys.executable, str(ROOT / "scripts" / "generate_contracts.py"), "--check"])
    from agent_runtime.contracts import validate_configuration
    operational = ROOT / "examples" / "operational"
    validate_configuration(json.loads((operational / "policy.example.json").read_text()),
                           json.loads((operational / "goal.example.json").read_text()))
    from reference_runtime.base import BaseEngine
    from reference_runtime.contracts import (
        CORE_CONTRACT,
        REFERENCE_CONTRACT,
        RUNTIME_PROFILE,
        VERIFICATION_PROFILE,
        load_json,
        validate_authority_model,
        validate_contract_set,
        validate_goal,
        validate_goal_against_roadmap,
        validate_policy,
        validate_release_state,
        validate_roadmap,
        validate_role_protocols,
    )
    from reference_runtime.schema_validation import (
        ARTIFACT_SCHEMAS,
        ARTIFACT_SCHEMA_PATTERNS,
        load_schema,
        validate_json_file,
    )

    schema_files = sorted((ROOT / "schemas").glob("*.schema.json"))
    check(bool(schema_files), "no JSON Schemas found")
    for path in schema_files:
        load_schema(path)

    static_pairs = (
        (ROOT / "config" / "contract-set.json", ROOT / "schemas" / "contract-set.schema.json"),
        (ROOT / "examples" / "goal.example.json", ROOT / "schemas" / "goal.schema.json"),
        (ROOT / "config" / "reference-policy.json", ROOT / "schemas" / "policy.schema.json"),
        (ROOT / "config" / "role-protocols.json", ROOT / "schemas" / "role-protocols.schema.json"),
        (PRODUCT / ".agent-control" / "authority-model.json", ROOT / "schemas" / "authority-model.schema.json"),
        (PRODUCT / ".agent-control" / "roadmap.json", ROOT / "schemas" / "roadmap.schema.json"),
        (PRODUCT / ".agent-control" / "release-state.json", ROOT / "schemas" / "release-state.schema.json"),
        (PRODUCT / ".agent-control" / "verification-probes.json", ROOT / "schemas" / "verification-probes.schema.json"),
    )
    for instance, schema in static_pairs:
        validate_json_file(instance, schema)

    contracts = load_json(ROOT / "config" / "contract-set.json")
    goal = load_json(ROOT / "examples" / "goal.example.json")
    policy = load_json(ROOT / "config" / "reference-policy.json")
    roadmap = load_json(PRODUCT / ".agent-control" / "roadmap.json")
    release_state = load_json(PRODUCT / ".agent-control" / "release-state.json")
    roles = load_json(ROOT / "config" / "role-protocols.json")
    authority_model = load_json(PRODUCT / ".agent-control" / "authority-model.json")

    validate_contract_set(contracts)
    validate_goal(goal)
    validate_policy(policy)
    validate_roadmap(roadmap)
    validate_release_state(release_state, roadmap)
    validate_goal_against_roadmap(goal, roadmap)
    validate_role_protocols(roles)
    validate_authority_model(authority_model)

    check(contracts["reference_contract"] == REFERENCE_CONTRACT, "reference contract drift")
    check(contracts["core_contract"] == CORE_CONTRACT, "core contract drift")
    check(contracts["verification_profile"] == VERIFICATION_PROFILE, "verification profile drift")
    check(contracts["runtime_profile"] == RUNTIME_PROFILE, "runtime profile drift")
    check(goal["autonomy"]["max_cycles"] <= policy["max_cycles"], "goal exceeds policy cycle authority")
    check(
        goal["autonomy"]["max_attempts_per_item"] <= policy["max_attempts_per_item"],
        "goal exceeds policy attempt authority",
    )

    ids = [row["id"] for row in roadmap["items"]]
    check(ids == ["EXAMPLE-001", "EXAMPLE-002"], "reference roadmap no longer demonstrates two dependent items")
    check(roadmap["items"][1]["dependencies"] == ["EXAMPLE-001"], "second roadmap item dependency drift")
    check(
        authority_model["artifacts"]["release-state.json"]["mutation"] == "controller-after-verified-effect",
        "release state is not controller-owned state authority",
    )
    check(
        authority_model["artifacts"]["architecture.md"]["enforcement"] == "reasoning-context",
        "context prose is being presented as machine policy",
    )

    scenario_schema = ROOT / "schemas" / "scenario.schema.json"
    scenarios = sorted((ROOT / "examples" / "scenarios").glob("*.json"))
    required = {
        "happy-path", "raw-outcome-forgery", "receipt-injection", "crash-recovery",
        "autonomous-two-item", "repair-loop", "dependency-blocked",
        "human-approve-resume", "human-reject-resume", "human-request-changes",
    }
    names = {path.stem for path in scenarios}
    check(required <= names, "core security/autonomy conformance scenarios missing")
    check("nonce-forgery" not in names, "obsolete nonce-forgery scenario returned")
    for path in scenarios:
        validate_json_file(path, scenario_schema)
        value = json.loads(path.read_text())
        check(value["name"] == path.stem, f"scenario identity drift: {path.name}")
        if path.stem == "raw-outcome-forgery":
            check(value.get("expectation") == "known-limit", "raw outcome must remain explicit known-limit")

    probes = load_json(PRODUCT / ".agent-control" / "verification-probes.json")
    probe_ids = [row["id"] for row in probes["baseline"] + probes["acceptance"]]
    for required_probe in (
        "greet-normalized", "greet-unicode", "greet-blank",
        "shout-normalized", "shout-unicode", "shout-blank",
    ):
        check(required_probe in probe_ids, f"verification probe missing: {required_probe}")
    for probe in probes["baseline"] + probes["acceptance"]:
        BaseEngine._validate_probe(probe)
        check("args" not in probe and "expect" not in probe, "legacy fixed probe format returned")

    for critical in (
        "request.json", "proposal.json", "merge-intent.json", "human-decision.json",
        "control-loop.json", "goal-evaluation.json", "contract-set.json",
    ):
        check(critical in ARTIFACT_SCHEMAS, f"critical evidence schema mapping missing: {critical}")
    pattern_samples = (
        "authority-snapshot-baseline.json",
        "protected-tests-candidate.json",
        "role-reviewer-example-001-attempt-01.json",
        "feedback-example-001-attempt-01.json",
        "release-transition-example-001.json",
        "human-decision-example-001-attempt-01.json",
        "test-baseline-example-001-cycle-01.json",
        "probe-baseline-example-001-cycle-01.json",
        "risk-decision-example-001-attempt-01.json",
        "merge-intent-example-001.json",
        "merge-evidence-example-001.json",
        "test-postmerge-example-001.json",
        "probe-postmerge-example-001.json",
        "postmerge-evidence-example-001.json",
    )
    for sample in pattern_samples:
        check(
            any(pattern.fullmatch(sample) for pattern, _ in ARTIFACT_SCHEMA_PATTERNS),
            f"pattern evidence schema mapping missing: {sample}",
        )


def validate_product_baseline_without_mutation() -> None:
    before = {
        path.relative_to(PRODUCT).as_posix(): path.read_bytes()
        for path in PRODUCT.rglob("*") if path.is_file()
    }
    with tempfile.TemporaryDirectory(prefix="reference-baseline-") as directory:
        copy = Path(directory) / "product"
        shutil.copytree(PRODUCT, copy)
        run([sys.executable, "-S", "ci/run_tests.py"], cwd=copy)
        junit = copy / "build" / "test-results" / "reference" / "TEST-reference.xml"
        check(junit.is_file(), "baseline JUnit missing")
        tests = list(ET.parse(junit).getroot().iter("testcase"))
        check(len(tests) == 3, f"expected 3 baseline tests, observed {len(tests)}")
    after = {
        path.relative_to(PRODUCT).as_posix(): path.read_bytes()
        for path in PRODUCT.rglob("*") if path.is_file()
    }
    check(before == after, "validator mutated source example")


def validate_authority_layout() -> None:
    from reference_runtime.contracts import digest_paths, matches_any

    policy = json.loads((ROOT / "config" / "reference-policy.json").read_text())
    snapshot = digest_paths(PRODUCT, policy["authority_paths"])
    check(bool(snapshot["files"]), "authority source snapshot would be empty")
    for required in (
        ".agent-control/authority-model.json",
        ".agent-control/roadmap.json",
        ".agent-control/release-state.json",
        ".agent-control/verification-probes.json",
    ):
        check(required in snapshot["files"], f"authority source missing from snapshot: {required}")
    for pattern in policy["authority_paths"]:
        check(
            any(matches_any(path, [pattern]) for path in snapshot["files"]),
            f"authority pattern matched no source files: {pattern}",
        )


def validate_python_and_shell() -> None:
    for base in (
        ROOT / "reference_runtime", ROOT / "agent_runtime", ROOT / "control_plane_core", ROOT / "scripts", ROOT / "tests",
        PRODUCT / "src", PRODUCT / "tests", PRODUCT / "ci",
    ):
        for path in base.rglob("*.py"):
            ast.parse(path.read_text(), filename=str(path))
    for path in (ROOT / "scripts").glob("*.sh"):
        run(["bash", "-n", str(path)])
    run(["bash", "-n", str(ROOT / "scripts" / "agentctl")])
    run(["bash", str(ROOT / "scripts" / "bootstrap-linux.sh"), "self-test"])


def validate_docs_claims() -> None:
    from reference_runtime.contract_ids import CONTRACT_SET
    readme = " ".join((ROOT / "README.md").read_text().lower().split())
    for key, value in CONTRACT_SET.items():
        if key != "schema":
            check(value in readme, f"README contract missing: {key}")
    check("deterministic fixtures" in readme[:2000], "fixture scope must appear at the beginning")
    check("goal reconciliation" in readme and "release-state transition" in readme, "README lost lifecycle scope")
    core = (ROOT / "docs/CORE-CONTRACT.md").read_text().lower()
    verification = (ROOT / "docs/VERIFICATION.md").read_text().lower()
    for action in ("approve", "reject", "request_changes"):
        check(action in core, f"human authority action undocumented: {action}")
    check("raw-outcome-forgery" in verification and "known-limit" in verification, "known verifier limitation disappeared")
    for name in ("ARCHITECTURE", "CORE-CONTRACT", "VERIFICATION", "OPERATIONS", "ADOPTION"):
        check(f"docs/{name.lower()}.md" in readme, f"missing primary guide: {name}")


def main(argv: list[str] | None = None) -> int:
    from reference_runtime.contracts import CORE_CONTRACT, REFERENCE_CONTRACT, RUNTIME_PROFILE, VERIFICATION_PROFILE

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
        "reference_contract": REFERENCE_CONTRACT,
        "core_contract": CORE_CONTRACT,
        "verification_profile": VERIFICATION_PROFILE,
        "runtime_profile": RUNTIME_PROFILE,
        "licensed": "Apache-2.0",
        "provenance": "Horistum",
        "baseline_tests": 0 if args.fast else 3,
        "source_tree_mutated": False,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
