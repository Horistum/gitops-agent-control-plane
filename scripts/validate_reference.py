#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
PRODUCT = ROOT / "examples" / "minimal-product"
FORBIDDEN_BRANDING = (
    "Flow" + "AI",
    "Flow" + "Ai",
    "Flow" + " Loop",
    "flow" + "-loop",
    "/" + "loop ",
    "Horistum/" + "Flow" + "Ai",
    "co" + "dex",
)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit("reference validation failed: " + message)


def run(argv: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess:
    p = subprocess.run(argv, cwd=cwd, text=True, capture_output=True)
    if p.returncode:
        raise SystemExit("reference validation failed: command failed: " + " ".join(argv) + "\nSTDOUT:\n" + p.stdout[-4000:] + "\nSTDERR:\n" + p.stderr[-4000:])
    return p


def validate_brand_neutrality() -> None:
    suffixes = {".md", ".py", ".sh", ".json", ".yml", ".yaml"}
    skip_parts = {".git", ".demo", "__pycache__", "build"}
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in suffixes:
            continue
        if any(part in skip_parts for part in path.parts):
            continue
        text = path.read_text(errors="replace")
        for token in FORBIDDEN_BRANDING:
            check(token not in text, f"internal/backend branding leaked into {path.relative_to(ROOT)}: {token}")


def validate_json() -> None:
    for base in (ROOT / "config", ROOT / "schemas", ROOT / "examples"):
        for path in base.rglob("*.json"):
            json.loads(path.read_text())
    goal = json.loads((ROOT / "examples" / "goal.example.json").read_text())
    policy = json.loads((ROOT / "config" / "reference-policy.json").read_text())
    from reference_runtime.contracts import validate_goal, validate_policy
    validate_goal(goal)
    validate_policy(policy)
    for name in ("goal", "policy", "plan", "state", "evidence"):
        schema = json.loads((ROOT / "schemas" / f"{name}.schema.json").read_text())
        check(schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema", f"{name} schema dialect drift")


def validate_product_baseline() -> None:
    p = run([sys.executable, "ci/run_tests.py"], cwd=PRODUCT)
    junit = PRODUCT / "build" / "test-results" / "reference" / "TEST-reference.xml"
    check(junit.is_file(), "baseline JUnit missing")
    root = ET.parse(junit).getroot()
    tests = list(root.iter("testcase"))
    check(len(tests) == 3, f"expected 3 baseline tests, observed {len(tests)}")
    identities = {(t.get("classname"), t.get("name")) for t in tests}
    check(len(identities) == 3, "baseline test identities are not unique")
    check("OK" in p.stderr or "OK" in p.stdout, "baseline runner did not report success")


def validate_authority_layout() -> None:
    expected = {"authority.md", "architecture.md", "roadmap.json", "release-state.json", "forbidden.json", "quality-gates.json"}
    actual = {p.name for p in (PRODUCT / ".agent-control").iterdir() if p.is_file()}
    check(expected <= actual, f"missing authority files: {sorted(expected-actual)}")
    policy = json.loads((ROOT / "config" / "reference-policy.json").read_text())
    check(".agent-control/**" in policy["authority_paths"], "authority namespace missing from policy")
    check(".agent-control/**" not in policy["allowed_paths"], "authority namespace entered write envelope")


def validate_python() -> None:
    for base in (ROOT / "reference_runtime", ROOT / "scripts", ROOT / "tests", PRODUCT / "src", PRODUCT / "tests", PRODUCT / "ci"):
        for path in base.rglob("*.py"):
            ast.parse(path.read_text(), filename=str(path))


def validate_shell() -> None:
    scripts = [ROOT / "scripts" / "agentctl", ROOT / "scripts" / "bootstrap-linux.sh", ROOT / "scripts" / "diagnose-linux.sh", ROOT / "scripts" / "cleanup-linux.sh"]
    for path in scripts:
        check(path.is_file(), f"missing shell entrypoint: {path.relative_to(ROOT)}")
        check(path.stat().st_mode & 0o111, f"not executable: {path.relative_to(ROOT)}")
        run(["bash", "-n", str(path)])
    run(["bash", str(ROOT / "scripts" / "bootstrap-linux.sh"), "self-test"])


def validate_workflow() -> None:
    workflow = (ROOT / ".github" / "workflows" / "reference-integrity.yml").read_text()
    for phrase in ("scripts/agentctl validate", "scripts/agentctl demo happy-path"):
        check(phrase in workflow, f"CI does not exercise {phrase}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--fast", action="store_true", help="Skip the product baseline; useful inside diagnostics.")
    a = p.parse_args(argv)
    validate_brand_neutrality()
    validate_json()
    validate_authority_layout()
    validate_python()
    validate_shell()
    validate_workflow()
    if not a.fast:
        validate_product_baseline()
    print(json.dumps({"passed": True, "reference_contract": "gitops-agent-control-plane/v2", "brand_neutral": True, "standalone": True, "baseline_tests": 0 if a.fast else 3}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
