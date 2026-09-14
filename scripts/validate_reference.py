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


def run(argv: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess:
    result = subprocess.run(argv, cwd=cwd, text=True, capture_output=True)
    if result.returncode:
        raise SystemExit(
            "reference validation failed: command failed: " + " ".join(argv)
            + "\nSTDOUT:\n" + result.stdout[-4000:]
            + "\nSTDERR:\n" + result.stderr[-4000:]
        )
    return result


def run_product() -> int:
    p = subprocess.run([sys.executable, "ci/run_tests.py"], cwd=PRODUCT)
    check(p.returncode == 0, "minimal product baseline is not green")
    xml = PRODUCT / "build" / "test-results" / "reference" / "TEST-reference.xml"
    check(xml.is_file(), "minimal product did not emit JUnit")
    cases = list(ET.parse(xml).getroot().iter("testcase"))
    check(len(cases) == 3, f"expected exactly 3 baseline testcase identities, observed {len(cases)}")
    identities = {(case.get("classname"), case.get("name")) for case in cases}
    check(len(identities) == 3, "baseline JUnit testcase identities are not unique")
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
    check((ROOT / "docs" / "LINUX.md").is_file(), "Linux runbook is missing")

    forbidden = ("FlowAI-Control", "Flow Loop", "Horistum/FlowAi-control")
    portable_docs = (
        "README.md", "docs/ARCHITECTURE.md", "docs/MODEL.md", "docs/POLICY.md",
        "docs/SECURITY.md", "docs/ADOPTION.md", "docs/OPERATIONS.md", "docs/LIMITATIONS.md",
        "docs/LINUX.md",
    )
    for relative in portable_docs:
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


def validate_shell() -> int:
    scripts = [
        ROOT / "scripts" / "agentctl",
        ROOT / "scripts" / "bootstrap-linux.sh",
        ROOT / "scripts" / "diagnose-linux.sh",
        ROOT / "scripts" / "uninstall-linux.sh",
        ROOT / "scripts" / "control.sh",
        ROOT / "scripts" / "submit-goal.sh",
    ]
    for path in scripts:
        check(path.is_file(), f"missing shell entry point: {path.relative_to(ROOT)}")
        check(path.stat().st_mode & 0o111 != 0, f"shell entry point is not executable: {path.relative_to(ROOT)}")
        check("set -E" in path.read_text() or "set -e" in path.read_text(),
              f"shell entry point is not fail-fast: {path.relative_to(ROOT)}")
        run(["bash", "-n", str(path)])

    run([str(ROOT / "scripts" / "bootstrap-linux.sh"), "self-test"])
    run([str(ROOT / "scripts" / "agentctl"), "self-test"])
    run([str(ROOT / "scripts" / "diagnose-linux.sh"), "--help"])
    run([str(ROOT / "scripts" / "uninstall-linux.sh"), "--help"])
    run([str(ROOT / "scripts" / "control.sh"), "--help"])
    run([str(ROOT / "scripts" / "submit-goal.sh"), "--help"])

    bootstrap = (ROOT / "scripts" / "bootstrap-linux.sh").read_text()
    check("apt-get" in bootstrap and "dnf" in bootstrap, "Linux bootstrap lost supported package-manager paths")
    uninstall = (ROOT / "scripts" / "uninstall-linux.sh").read_text()
    check("Remote GitHub" in uninstall and "--purge-state" in uninstall,
          "uninstall safety contract drift")
    return len(scripts)


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
    shell_scripts = validate_shell()
    compile_python()
    print(json.dumps({
        "passed": True,
        "baseline_tests": tests,
        "shell_entrypoints": shell_scripts,
        "reference_contract": "gitops-agent-control-plane/v1",
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
