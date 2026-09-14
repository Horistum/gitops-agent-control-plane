#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
PHASES = {
    "discovery", "architect", "test_design", "chief_plan", "developer",
    "tester", "reviewer", "challenge_review", "architect_accept", "chief_accept",
}


def check(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit("reference validation failed: " + message)


def main() -> int:
    compat = json.loads((ROOT / "COMPATIBILITY.json").read_text())
    source = compat["flowai_control"]
    check(source["version"] == "0.3.0", "compatibility version drift")
    check(bool(re.fullmatch(r"[0-9a-f]{40}", source["commit"])), "controller commit is not full SHA")

    policy = json.loads((ROOT / "config" / "policy.template.json").read_text())
    check(policy["product_repo"] != policy["control_repo"], "template must separate product/control repos")
    check(set(policy["phase_context_paths"]) == PHASES, "phase_context_paths key drift")
    check(set(policy["phase_context_bytes"]) == PHASES, "phase_context_bytes key drift")
    approved = set(policy["context_paths"])
    for phase, paths in policy["phase_context_paths"].items():
        check(set(paths) <= approved, f"{phase} context contains non-authority path")
    check(policy["test_commands"] == [["python3", "ci/run_tests.py"]], "example test command drift")
    check(policy["required_checks"] == [{"name": "flowai-reference-ci", "app_id": 15368}],
          "required check drift")
    check(policy["postmerge_checks"] == policy["required_checks"], "postmerge check drift")
    check(policy["billing"] == {
        "provider": "chatgpt", "credit_mode": "included_then_purchased", "api_fallback": False
    }, "billing contract drift")
    check(policy["test_image"].startswith("REPLACE_TEST_IMAGE@sha256:"), "test image must stay explicit placeholder")

    issue = (ROOT / ".github" / "ISSUE_TEMPLATE" / "flow-loop-goal.yml").read_text()
    check(issue.count("<!-- flow-loop-goal:v1 -->") == 1, "Goal Issue marker drift")
    for label in (
        "Cíl", "Položky roadmapy", "Nejvyšší přijatelné riziko", "Automatický merge",
        "Podmínka dokončení", "Zakázané směry", "Potvrzení"
    ):
        check(f"label: {label}" in issue, f"Goal Issue protocol label missing: {label}")

    workflow = (ROOT / "examples" / "minimal-product" / ".github" / "workflows" / "ci.yml").read_text()
    check("name: flowai-reference-ci" in workflow, "product workflow check identity drift")

    product = ROOT / "examples" / "minimal-product"
    build = product / "build"
    if build.exists():
        shutil.rmtree(build)
    p = subprocess.run([sys.executable, "ci/run_tests.py"], cwd=product)
    check(p.returncode == 0, "minimal product baseline failed")
    xml = product / "build" / "test-results" / "reference" / "TEST-reference.xml"
    check(xml.is_file(), "minimal product did not emit expected JUnit XML")
    tree = ET.parse(xml).getroot()
    check(int(tree.attrib.get("tests", "0")) >= 1, "JUnit reports zero tests")
    check(int(tree.attrib.get("failures", "0")) == 0 and int(tree.attrib.get("errors", "0")) == 0,
          "JUnit reports baseline failures")

    with tempfile.TemporaryDirectory(prefix="reference-policy-") as d:
        out = Path(d) / "policy.json"
        fake_image = "docker.io/library/python:3.13-slim@sha256:" + "1" * 64
        p = subprocess.run([
            sys.executable, str(ROOT / "scripts" / "render_policy.py"),
            "--product-repo", "owner/product",
            "--control-repo", "owner/control",
            "--owner", "owner",
            "--command-issue", "1",
            "--test-image", fake_image,
            "--codex-version", "codex-cli reference-test",
            "--output", str(out),
        ])
        check(p.returncode == 0 and out.is_file(), "policy renderer smoke failed")
        rendered = json.loads(out.read_text())
        check(rendered["product_repo"] == "owner/product", "renderer product repo mismatch")
        check(rendered["control_repo"] == "owner/control", "renderer control repo mismatch")
        check(rendered["test_image"] == fake_image, "renderer image mismatch")

    if build.exists():
        shutil.rmtree(build)
    print(json.dumps({
        "passed": True,
        "controller_source": source["repository"],
        "controller_commit": source["commit"],
        "minimal_product_tests": int(tree.attrib["tests"]),
        "goal_issue_protocol": "v1",
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
