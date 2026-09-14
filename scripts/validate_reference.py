#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import py_compile
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
PRODUCT = ROOT / "examples" / "minimal-product"


def check(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit("reference validation failed: " + message)


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def run_product() -> int:
    p = subprocess.run([sys.executable, "ci/run_tests.py"], cwd=PRODUCT)
    check(p.returncode == 0, "minimal product baseline is not green")
    xml = PRODUCT / "build" / "test-results" / "reference" / "TEST-reference.xml"
    check(xml.is_file(), "minimal product did not emit JUnit")
    cases = list(ET.parse(xml).getroot().iter("testcase"))
    check(len(cases) == 3, f"expected exactly 3 baseline testcase identities, observed {len(cases)}")
    return len(cases)


def validate_policy() -> None:
    template = json.loads((ROOT / "config" / "policy.template.json").read_text())
    check(template["product_repo"] != template["control_repo"], "template repository identities collapsed")
    expected = [{"name": "agent-control-reference-ci", "app_id": 15368}]
    check(template["required_checks"] == expected and template["postmerge_checks"] == expected,
          "trusted CI identity drift")
    check(template["github_goals"]["allowed_item_patterns"] == ["EXAMPLE-*"], "goal pattern drift")
    check(any(x.startswith(".agent-control/") for x in template["context_paths"]), "authority namespace missing")
    check(not any(x.startswith(".agent-control/") for x in template["allowed_paths"]),
          "authority files accidentally entered write envelope")

    renderer = load("render_policy", ROOT / "scripts" / "render_policy.py")
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "policy.json"
        argv = [
            "--product-repo", "example/product", "--control-repo", "example/control",
            "--owner", "owner", "--command-issue", "1", "--controller-id", "reference-primary",
            "--test-image", "localhost/reference@sha256:" + "1"*64,
            "--codex-version", "model-cli 1.0", "--output", str(out),
        ]
        check(renderer.main(argv) == 0 and out.is_file(), "policy renderer smoke failed")
        check(json.loads(out.read_text())["required_checks"] == expected, "rendered policy CI identity drift")


def validate_goal_adapter() -> None:
    adapter = load("submit_goal", ROOT / "scripts" / "submit_goal.py")
    goal = json.loads((ROOT / "examples" / "goal.example.json").read_text())
    title, body = adapter.backend_issue(goal)
    check(title.startswith("[Flow Loop Goal]"), "backend goal protocol title drift")
    check(body.count("<!-- flow-loop-goal:v1 -->") == 1, "backend goal marker drift")
    for label in ("Cíl", "Položky roadmapy", "Nejvyšší přijatelné riziko", "Automatický merge",
                  "Podmínka dokončení", "Zakázané směry", "Potvrzení"):
        check(f"### {label}" in body, f"backend goal protocol section missing: {label}")
    check("EXAMPLE-001" in body, "portable goal item lost in translation")


def validate_control_adapter() -> None:
    adapter = load("control", ROOT / "scripts" / "control.py")
    parser = adapter.parser()
    rows = {
        ("pause",): "/loop pause",
        ("drain",): "/loop drain",
        ("resume",): "/loop resume",
        ("refresh",): "/loop refresh",
        ("activate", "--fingerprint", "abc"): "/loop activate abc",
        ("retry", "--task", "EXAMPLE-001"): "/loop retry EXAMPLE-001",
        ("approve", "--task", "EXAMPLE-001", "--hash", "h"): "/loop approve EXAMPLE-001 h",
        ("replan", "--task", "EXAMPLE-001", "--hash", "h"): "/loop replan EXAMPLE-001 h",
        ("cancel-goal", "--goal", "GOAL-1", "--hash", "h"): "/loop cancel-goal GOAL-1 h",
    }
    for argv, expected in rows.items():
        args = parser.parse_args(["--dry-run", *argv])
        check(adapter.backend_command(args) == expected, f"operator mapping drift: {argv}")


def validate_governance() -> None:
    mod = load("governance", ROOT / "scripts" / "product_governance.py")
    value = mod.desired([{"name":"agent-control-reference-ci","app_id":15368}])
    text = json.dumps(value)
    check("agent-control-reference-ci" in text and "15368" in text, "governance lost trusted check identity")
    check(value["name"] == "Agent Control main protection", "governance identity drift")


def validate_files() -> None:
    required = [
        ".agent-control/authority.md", ".agent-control/architecture.md", ".agent-control/roadmap.yaml",
        ".agent-control/release-state.yaml", ".agent-control/forbidden.yaml", ".agent-control/quality-gates.yaml",
    ]
    for path in required:
        check((PRODUCT / path).is_file(), f"missing example authority file: {path}")
    check(not (PRODUCT / ".flow-agent").exists(), "backend-specific authority namespace still exists")
    workflow = (PRODUCT / ".github" / "workflows" / "ci.yml").read_text()
    check("name: agent-control-reference-ci" in workflow, "product workflow check identity drift")
    check("EXAMPLE-001" in (PRODUCT / ".agent-control" / "roadmap.yaml").read_text(), "roadmap id drift")
    check(not (ROOT / ".github" / "ISSUE_TEMPLATE" / "flow-loop-goal.yml").exists(),
          "backend-specific goal form leaked into public UI")

    forbidden = ("FlowAI-Control", "Flow Loop", "Horistum/FlowAi-control")
    for relative in ("README.md", "docs/ARCHITECTURE.md", "docs/MODEL.md", "docs/POLICY.md",
                     "docs/SECURITY.md", "docs/ADOPTION.md", "docs/OPERATIONS.md", "docs/LIMITATIONS.md"):
        text = (ROOT / relative).read_text()
        for token in forbidden:
            check(token not in text, f"backend branding leaked into portable narrative: {relative}: {token}")


def validate_compatibility() -> None:
    compat = json.loads((ROOT / "COMPATIBILITY.json").read_text())
    runtime = compat["runtime_adapter"]
    check(compat["reference_contract"] == "gitops-agent-control-plane/v1", "reference contract drift")
    check(len(runtime["commit"]) == 40 and all(c in "0123456789abcdef" for c in runtime["commit"]),
          "runtime commit is not an exact Git SHA")
    check(runtime["service_name"] == "agent-control-plane.service", "service identity drift")


def compile_python() -> None:
    for base in (ROOT / "scripts", PRODUCT / "ci", PRODUCT / "src", PRODUCT / "tests"):
        for path in base.rglob("*.py"):
            py_compile.compile(str(path), doraise=True)


def main() -> int:
    tests = run_product()
    validate_policy()
    validate_goal_adapter()
    validate_control_adapter()
    validate_governance()
    validate_files()
    validate_compatibility()
    compile_python()
    print(json.dumps({"passed": True, "baseline_tests": tests,
                      "reference_contract": "gitops-agent-control-plane/v1"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
