#!/usr/bin/env python3
"""Check publication source files, not live GitHub settings or legal clearance."""
from __future__ import annotations

import argparse
import ast
import html
import json
from pathlib import Path
import re
import sys
import tomllib
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = ("LICENSE", "NOTICE", "TRADEMARKS.md", "MAINTAINERS.md", "CONTRIBUTING.md",
            "SUPPORT.md", "README.md", "MANIFEST.in", ".github/SECURITY.md",
            "docs/PUBLICATION.md", "docs/PROVENANCE.md", "docs/RELEASES.md",
            "docs/GITHUB-SETTINGS.md", ".github/CODEOWNERS", ".github/repository-settings.json",
            ".github/dependabot.yml", ".github/PULL_REQUEST_TEMPLATE.md")
PRIVATE_DOC = re.compile(r"(?i:flowai(?:[-_/ ]?control)?)|flow_loop|AR-04C|Legion|\bFlow\b")
LOCAL_LINK = re.compile(r"\[[^\]\n]*\]\(([^\s)]+)(?:\s+['\"][^)]*)?\)")


def markdown_anchors(text: str) -> set[str]:
    """Resolve headings and explicit IDs used by this repository's Markdown.

    Fenced examples do not define headings. Duplicate heading IDs retain GitHub's
    numeric suffixes. This is not a complete Markdown renderer.
    """
    anchors: set[str] = set()
    fence = None
    for line in text.splitlines():
        marker = re.match(r"^\s{0,3}(`{3,}|~{3,})", line)
        if marker:
            token = marker.group(1)
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
            continue
        if fence is not None:
            continue
        for explicit in re.findall(r'<[^>]+\b(?:id|name)=["\']([^"\']+)["\'][^>]*>', line):
            anchors.add(explicit)
        heading = re.match(r"^\s{0,3}#{1,6}\s+(.+?)(?:\s+#+)?\s*$", line)
        if not heading:
            continue
        title = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", heading.group(1))
        title = html.unescape(re.sub(r"<[^>]*>", "", title)).lower()
        slug = re.sub(r"[^\w\s-]", "", title).replace(" ", "-")
        candidate, suffix = slug, 0
        while candidate in anchors:
            suffix += 1
            candidate = f"{slug}-{suffix}"
        anchors.add(candidate)
    return anchors


def inspect_source(root: Path) -> list[str]:
    errors: list[str] = []
    for name in REQUIRED:
        path = root / name
        if path.is_symlink() or not path.is_file():
            errors.append(f"Missing regular publication file: {name}")
    if errors:
        return errors
    try:
        project = tomllib.loads((root / "pyproject.toml").read_text())["project"]
        version = project["version"]
        if not re.fullmatch(r"\d+\.\d+\.\d+", version):
            errors.append("Distribution version must be an explicit stable SemVer")
        if project.get("license") != "Apache-2.0" or set(project.get("license-files", [])) != {"LICENSE", "NOTICE", "TRADEMARKS.md"}:
            errors.append("SPDX license or explicit legal file inventory drift")
        if project.get("readme") != "README.md" or not project.get("authors") or not project.get("maintainers"):
            errors.append("Distribution README or maintainer metadata missing")
        if not {"Repository", "Documentation", "Issues", "Changelog", "Security"} <= project.get("urls", {}).keys():
            errors.append("Distribution project URLs missing")
        assignments = {}
        for node in ast.parse((root / "control_plane_core/__init__.py").read_text()).body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "__version__":
                        assignments[target.id] = ast.literal_eval(node.value)
        if assignments.get("__version__") != version:
            errors.append("Core and distribution version differ")
        if f"Version {version} includes" not in (root / "README.md").read_text():
            errors.append("README current version differs from distribution")
        if f"Current distribution: **{version}**." not in (root / "docs/RELEASES.md").read_text():
            errors.append("Release policy current version differs from distribution")
        if (root / "NOTICE").read_bytes() != (root / "control_plane_core/NOTICE.md").read_bytes():
            errors.append("Vendored core NOTICE differs from root NOTICE")
        if (root / "LICENSE").read_bytes() != (root / "control_plane_core/LICENSE.md").read_bytes():
            errors.append("Vendored core license differs from root LICENSE")
        settings = json.loads((root / ".github/repository-settings.json").read_text())
        if settings.get("schema") != 1 or not settings.get("required_checks"):
            errors.append("Repository settings contract is incomplete")
        if any(not isinstance(row.get("app_id"), int) or not row.get("context") for row in settings.get("required_checks", [])):
            errors.append("Required checks must bind context and GitHub App identity")
    except (KeyError, ValueError, TypeError, OSError) as exc:
        errors.append(f"Invalid publication metadata: {type(exc).__name__}")

    documents = list(root.glob("*.md"))
    for directory in ("docs", "validation", ".github", "examples", "schemas"):
        documents.extend((root / directory).rglob("*.md"))
    for path in sorted(documents):
        if any(part in {".demo", "__pycache__", "build"} for part in path.relative_to(root).parts):
            continue
        text = path.read_text(encoding="utf-8")
        if PRIVATE_DOC.search(text):
            errors.append(f"Private consumer identity/deployment detail in public document: {path.relative_to(root)}")
        for link in LOCAL_LINK.findall(text):
            parsed = urlsplit(link.strip("<>"))
            if parsed.scheme or parsed.netloc or not (parsed.path or parsed.fragment):
                continue
            target = (path.parent / unquote(parsed.path)).resolve() if parsed.path else path.resolve()
            if not target.is_relative_to(root.resolve()) or not target.exists():
                errors.append(f"Broken or outside-repository document link: {path.relative_to(root)} -> {link}")
            elif parsed.fragment and target.is_file() and target.suffix.lower() == ".md":
                if unquote(parsed.fragment) not in markdown_anchors(target.read_text(encoding="utf-8")):
                    errors.append(f"Broken document heading link: {path.relative_to(root)} -> {link}")

    for name in ("bug_report.yml", "feature_request.yml", "branding_permission.yml"):
        path = root / ".github/ISSUE_TEMPLATE" / name
        if not path.is_file() or "body:" not in path.read_text():
            errors.append(f"Missing usable issue form: {name}")
    for path in sorted((root / ".github/workflows").glob("*.yml")):
        text = path.read_text()
        # This is a bounded lint rule, not a general YAML/GitHub policy verifier.
        for action in re.findall(r"(?m)^\s*-?\s*uses:\s*([^\s#]+)", text):
            if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+@[0-9a-f]{40}", action):
                errors.append(f"Unpinned or unsupported action in {path.name}: {action}")
        if re.search(r"(?m)^\s*(pull_request_target|workflow_run):", text):
            errors.append(f"Privileged untrusted-code trigger requires separate review: {path.name}")
        if "contents: read" not in text or "persist-credentials: false" not in text:
            errors.append(f"Missing read-only/ephemeral-checkout controls: {path.name}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        errors = inspect_source(args.root.resolve())
    except (OSError, UnicodeError) as exc:
        errors = [f"Unreadable source input: {type(exc).__name__}"]
    report = {"schema": 1, "scope": "repository-files-only", "passed": not errors,
              "errors": errors, "live_github_settings_verified": False,
              "history_secrets_reviewed": False, "legal_clearance_verified": False,
              "public_visibility_authorized": False}
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
