"""Executable regression checks for publication tooling, not legal clearance."""
from __future__ import annotations

from copy import deepcopy
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


source = module("check_publication")
distribution = module("check_distribution")
settings = module("github_settings")
history = module("scan_history")


class SourceChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name, data in distribution.source_files(ROOT).items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

    def test_current_source_is_consistent(self):
        self.assertEqual([], source.inspect_source(self.root))

    def test_version_and_legal_drift_are_rejected(self):
        (self.root / "control_plane_core/NOTICE.md").write_text("changed")
        readme = self.root / "README.md"
        readme.write_text(readme.read_text().replace("Version " + tomllib.loads((self.root / "pyproject.toml").read_text())["project"]["version"] + " includes", "Version 999.999.999 includes"))
        errors = source.inspect_source(self.root)
        self.assertTrue(any("NOTICE" in x for x in errors))
        self.assertTrue(any("README current version" in x for x in errors))

    def test_broken_links_private_consumer_and_missing_forms_are_rejected(self):
        (self.root / "docs/bad.md").write_text("FlowAi-control deployment [guide](missing.md)\n")
        (self.root / ".github/ISSUE_TEMPLATE/bug_report.yml").unlink()
        errors = source.inspect_source(self.root)
        for phrase in ("Private consumer", "Broken", "Missing usable issue form"):
            self.assertTrue(any(phrase in x for x in errors), errors)

    def test_unpinned_action_and_privileged_trigger_are_rejected(self):
        (self.root / ".github/workflows/bad.yml").write_text("on:\n  pull_request_target:\njobs:\n  run:\n    steps:\n      - uses: actions/checkout@v5\n")
        errors = source.inspect_source(self.root)
        self.assertTrue(any("Unpinned" in x for x in errors))
        self.assertTrue(any("Privileged" in x for x in errors))

    def test_source_selection_never_follows_links_or_includes_local_state(self):
        (self.root / ".state").mkdir()
        (self.root / ".state/private.json").write_text("private")
        self.assertNotIn(".state/private.json", distribution.source_files(self.root))
        (self.root / "docs/link.md").symlink_to(self.root / "LICENSE")
        with self.assertRaisesRegex(ValueError, "symlink"):
            distribution.source_files(self.root)

    def test_metadata_missing_license_cannot_pass(self):
        path = self.root / "pyproject.toml"
        path.write_text(path.read_text().replace('license = "Apache-2.0"', 'license = "MIT"'))
        self.assertTrue(any("SPDX" in x for x in source.inspect_source(self.root)))


class ArchiveChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_archive_paths_fail_closed(self):
        for name in ("../secret", "/root/file", "a/../../file", "a\\file", "a/.git/config", ""):
            with self.subTest(name=name), self.assertRaises(ValueError):
                distribution.member_path(name)

    def test_source_archive_rejects_links_and_duplicate_members(self):
        for mode in ("link", "duplicate"):
            path = self.root / f"{mode}.tar.gz"
            with tarfile.open(path, "w:gz") as archive:
                item = tarfile.TarInfo("package/file")
                if mode == "link":
                    item.type, item.linkname = tarfile.SYMTYPE, "/etc/passwd"
                    archive.addfile(item)
                else:
                    item.size = 1
                    archive.addfile(item, io.BytesIO(b"a"))
                    archive.addfile(item, io.BytesIO(b"b"))
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                distribution.read_sdist(path)

    def test_wheel_rejects_link_duplicate_and_size_overflow(self):
        link = self.root / "link.whl"
        with zipfile.ZipFile(link, "w") as archive:
            item = zipfile.ZipInfo("module/link")
            item.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(item, "/etc/passwd")
        with self.assertRaisesRegex(ValueError, "Links"):
            distribution.read_wheel(link)
        duplicate = self.root / "duplicate.whl"
        with zipfile.ZipFile(duplicate, "w") as archive:
            archive.writestr("module/file", "a")
            archive.writestr("module/./file", "b")
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            distribution.read_wheel(duplicate)
        with patch.object(distribution, "MAX_BYTES", 1):
            with self.assertRaises(ValueError):
                distribution.read_wheel(duplicate)

    def fixture(self):
        expected = {"pyproject.toml": b'[project]\nname = "example"\nversion = "1.2.3"\nrequires-python = ">=3.11"\n[project.scripts]\nagent = "agent_runtime.cli:main"\n',
                    "README.md": b"Example description", "LICENSE": b"license", "NOTICE": b"notice", "TRADEMARKS.md": b"marks",
                    "agent_runtime/cli.py": b"def main(): pass\n"}
        prefix = "example-1.2.3.dist-info/"
        metadata = ("Metadata-Version: 2.4\nName: example\nVersion: 1.2.3\nLicense-Expression: Apache-2.0\n"
                    "Requires-Python: >=3.11\nDescription-Content-Type: text/markdown\n"
                    "License-File: LICENSE\nLicense-File: NOTICE\nLicense-File: TRADEMARKS.md\n\nExample description").encode()
        wheel = {prefix + "METADATA": metadata, prefix + "entry_points.txt": b"[console_scripts]\nagent = agent_runtime.cli:main\n",
                 "agent_runtime/cli.py": expected["agent_runtime/cli.py"]}
        wheel.update({prefix + "licenses/" + name: expected[name] for name in distribution.LEGAL_FILES})
        return expected, wheel

    def test_archive_validation_checks_legal_metadata_and_unexpected_content(self):
        expected, wheel = self.fixture()
        with patch.object(distribution, "read_sdist", return_value=expected), patch.object(distribution, "read_wheel", return_value=wheel):
            self.assertEqual("1.2.3", distribution.validate_archives(None, None, expected)["version"])
        for mutation in ("notice", "version", "dependency", "extra", "source-extra"):
            installed, archived = deepcopy(wheel), deepcopy(expected)
            key = "example-1.2.3.dist-info/METADATA"
            if mutation == "notice":
                installed.pop("example-1.2.3.dist-info/licenses/NOTICE")
            elif mutation == "version":
                installed[key] = installed[key].replace(b"Version: 1.2.3", b"Version: 9.0.0")
            elif mutation == "dependency":
                installed[key] = b"Requires-Dist: private-package\n" + installed[key]
            elif mutation == "extra":
                installed["agent_runtime/.env"] = b"private"
            else:
                archived[".env"] = b"private"
            with self.subTest(mutation=mutation), patch.object(distribution, "read_sdist", return_value=archived), patch.object(distribution, "read_wheel", return_value=installed), self.assertRaises(ValueError):
                distribution.validate_archives(None, None, expected)

    def test_build_environment_does_not_inherit_credentials_or_pythonpath(self):
        with patch.dict(os.environ, {"GH_TOKEN": "fixture-value", "PYTHONPATH": "/private", "PIP_INDEX_URL": "https://private.invalid"}):
            env = distribution.clean_env(self.root)
        self.assertFalse({"GH_TOKEN", "PYTHONPATH", "PIP_INDEX_URL"} & env.keys())
        self.assertEqual("1", env["PIP_NO_INDEX"])

    def test_distribution_output_must_not_mutate_source_or_replace_evidence(self):
        with self.assertRaisesRegex(ValueError, "outside"):
            distribution.check_distribution(ROOT, ROOT / "dist")
        (self.root / "prior-report").write_text("keep")
        with self.assertRaisesRegex(ValueError, "new or empty"):
            distribution.check_distribution(ROOT, self.root)


class SettingsChecks(unittest.TestCase):
    def setUp(self):
        self.config = settings.load_config()
        self.sha = "a" * 40

    def response(self, data=None, status=200):
        return {"status": status, "data": data}

    def observations(self, private=False):
        config = self.config
        protection = {"required_status_checks": {"strict": True, "checks": deepcopy(config["required_checks"])},
                      "required_pull_request_reviews": {"required_approving_review_count": config["minimum_reviews"],
                                                       "dismiss_stale_reviews": True, "bypass_pull_request_allowances": {}},
                      "enforce_admins": {"enabled": True}, "required_conversation_resolution": {"enabled": True},
                      "allow_force_pushes": {"enabled": False}, "allow_deletions": {"enabled": False},
                      "required_linear_history": {"enabled": False}}
        tags = {"target": "tag", "enforcement": "active", "bypass_actors": [], "rules": [{"type": "update"}, {"type": "deletion"}],
                "conditions": {"ref_name": {"include": ["refs/tags/v*"], "exclude": []}}}
        repo = {"full_name": config["repository"], "id": config["repository_id"], "default_branch": config["branch"], "private": private,
                "permissions": {"admin": True}, "security_and_analysis": {k: {"status": "enabled"} for k in ("secret_scanning", "secret_scanning_push_protection")}, **config["metadata"]}
        return {"repository": self.response(repo), "branch": self.response({"name": "main", "commit": {"sha": self.sha}, "protected": True}),
                "protection": self.response(protection), "topics": self.response({"names": config["topics"]}),
                "workflow_permissions": self.response({"default_workflow_permissions": "read", "can_approve_pull_request_reviews": False}),
                "actions_permissions": self.response({"enabled": True}), "fork_approval": self.response({"approval_policy": "all_external_contributors"}),
                "private_reporting": self.response({"enabled": True}), "dependabot_alerts": self.response(status=204),
                "branch_rules": self.response([]), "tag_rule": self.response(tags)}

    def test_config_cannot_introduce_visibility_or_unsupported_metadata(self):
        config = deepcopy(self.config)
        config["metadata"]["visibility"] = "public"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text(json.dumps(config))
            with self.assertRaisesRegex(ValueError, "Unsupported"):
                settings.load_config(path)

    def test_verified_settings_are_distinct_from_publication_authorization(self):
        data = self.observations()
        before = deepcopy(data)
        report = settings.audit(self.config, data)
        self.assertTrue(report["settings_passed"])
        self.assertFalse(report["public_visibility_authorized"])
        self.assertFalse(report["settings_changed"])
        self.assertEqual(before, data)
        private = settings.audit(self.config, self.observations(private=True))
        self.assertFalse(private["settings_passed"])
        self.assertEqual("deferred", next(x["state"] for x in private["controls"] if x["key"] == "private_reporting"))

    def test_inaccessible_or_ruleset_controlled_protection_remains_unknown(self):
        for status, protected in ((403, False), (404, True), (500, False)):
            data = self.observations()
            data["protection"] = self.response(status=status)
            data["branch"]["data"]["protected"] = protected
            report = settings.audit(self.config, data)
            self.assertEqual("unknown", next(x["state"] for x in report["controls"] if x["key"] == "protection"))
            self.assertFalse(report["settings_passed"])

    def test_stronger_protection_is_observed_without_modification(self):
        data = self.observations()
        protection = data["protection"]["data"]
        protection["required_pull_request_reviews"].update(required_approving_review_count=2, require_code_owner_reviews=True, require_last_push_approval=True)
        protection["required_status_checks"]["checks"].append({"context": "extra", "app_id": 123})
        before = deepcopy(data)
        self.assertTrue(settings.audit(self.config, data)["settings_passed"])
        self.assertEqual(before, data)

    def test_conflicting_linear_history_wrong_app_or_bypass_cannot_pass(self):
        for mutation in ("classic-linear", "ruleset-linear", "app", "bypass"):
            data = self.observations()
            protection = data["protection"]["data"]
            if mutation == "classic-linear":
                protection["required_linear_history"]["enabled"] = True
            elif mutation == "ruleset-linear":
                data["branch_rules"]["data"] = [{"type": "required_linear_history"}]
            elif mutation == "app":
                protection["required_status_checks"]["checks"][0]["app_id"] = 456
            else:
                protection["required_pull_request_reviews"]["bypass_pull_request_allowances"] = {"users": [{"login": "bypass"}]}
            with self.subTest(mutation=mutation):
                self.assertFalse(settings.audit(self.config, data)["settings_passed"])

    def test_wrong_repository_branch_or_sha_cannot_be_audited_as_valid(self):
        for mutation in ("repository", "branch", "sha"):
            data = self.observations()
            if mutation == "repository":
                data["repository"]["data"]["id"] += 1
            elif mutation == "branch":
                data["branch"]["data"]["name"] = "other"
            else:
                data["branch"]["data"]["commit"]["sha"] = "invalid"
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                settings.audit(self.config, data)

    def test_transport_only_issues_get_and_never_echoes_raw_denial(self):
        api = settings.GhApi(self.config["repository"])
        for stdout, code, status in (("HTTP/2.0 403 Forbidden\nContent-Type: application/json\n\n{\"message\":\"sensitive\"}", 1, 403),
                                     ("HTTP/2.0 204 No Content\nDate: today\n\n", 0, 204),
                                     ("HTTP/2.0 200 OK\nDate: today\n\n{}", 1, 0)):
            with patch.object(settings.subprocess, "run", return_value=subprocess.CompletedProcess([], code, stdout, "sensitive")) as run:
                response = api.get(api.prefix)
            self.assertEqual(status, response["status"])
            self.assertNotIn("sensitive", json.dumps(response))
            argv = run.call_args.args[0]
            self.assertEqual("GET", argv[argv.index("--method") + 1])
            self.assertNotIn("--input", argv)
        with self.assertRaises(ValueError):
            api.get("repos/other/project")
        self.assertFalse(hasattr(api, "request"))
        self.assertFalse(hasattr(settings, "apply"))

    def test_tag_exemptions_and_missing_rules_fail_the_audit(self):
        for mutation in ("missing", "bypass", "exclusion", "inactive"):
            data = self.observations()
            rule = data["tag_rule"]["data"]
            if mutation == "missing":
                data["tag_rule"]["data"] = None
            elif mutation == "bypass":
                rule["bypass_actors"] = [{"actor_id": 1}]
            elif mutation == "exclusion":
                rule["conditions"]["ref_name"]["exclude"] = ["refs/tags/v1*"]
            else:
                rule["enforcement"] = "disabled"
            with self.subTest(mutation=mutation):
                self.assertFalse(settings.audit(self.config, data)["settings_passed"])

    def test_explicitly_unprotected_branch_and_unreadable_alerts_are_not_success(self):
        data = self.observations()
        data["protection"] = self.response(status=404)
        data["branch"]["data"]["protected"] = False
        data["dependabot_alerts"] = self.response(status=404)
        states = {x["key"]: x["state"] for x in settings.audit(self.config, data)["controls"]}
        self.assertEqual("fail", states["protection"])
        self.assertEqual("unknown", states["dependabot_alerts"])

    def test_paginated_read_refuses_incomplete_collections(self):
        api = settings.GhApi(self.config["repository"])
        with patch.object(api, "get", side_effect=[{"status": 200, "data": [1], "has_next": True}, {"status": 403, "data": None}]):
            response = api.pages(api.prefix + "/rulesets")
        self.assertIsNone(response["data"])
        self.assertEqual(403, response["status"])


class HistoryChecks(unittest.TestCase):
    def test_normalized_evidence_never_contains_match_secret_or_commit_message(self):
        raw = [{"Commit": "a" * 40, "RuleID": "example-rule", "File": "example.py", "StartLine": 3,
                "Secret": "sensitive-value", "Match": "sensitive-value", "Message": "private message", "Author": "private author"}]
        findings = history.normalize_findings(raw)
        self.assertEqual({"commit", "rule", "path", "line", "fingerprint"}, set(findings[0]))
        self.assertNotIn("sensitive", json.dumps(findings))
        self.assertNotIn("private", json.dumps(findings))

    def test_invalid_scanner_locations_fail_closed(self):
        valid = {"Commit": "a" * 40, "RuleID": "rule", "File": "file", "StartLine": 1}
        for key, value in (("Commit", "unknown"), ("File", "file\nsecret"), ("StartLine", True), ("StartLine", 0), ("RuleID", "rule/secret")):
            with self.subTest(key=key), self.assertRaises(ValueError):
                history.normalize_findings([{**valid, key: value}])
        with self.assertRaises(ValueError):
            history.normalize_findings({})

    def fixture(self, directory):
        root = Path(directory) / "repository"
        root.mkdir()
        def git(*args):
            return subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, check=True).stdout.strip()
        git("init", "-b", "main")
        git("config", "user.email", "fixture@example.invalid")
        git("config", "user.name", "Fixture")
        (root / "file").write_text("fixture")
        git("add", ".")
        git("commit", "-m", "Fixture")
        git("checkout", "--detach")
        (root / "file").write_text("detached fixture")
        git("commit", "-am", "Detached fixture")
        scanner = Path(directory) / "gitleaks"
        scanner.write_text('#!' + sys.executable + '\nimport json, pathlib, sys\n'
                           'if sys.argv[1] == "version":\n    print("8.30.1")\nelse:\n'
                           '    assert "--log-opts=--full-history -m --all HEAD" in sys.argv\n'
                           '    assert "--ignore-gitleaks-allow" in sys.argv\n'
                           '    output = next(x.split("=", 1)[1] for x in sys.argv if x.startswith("--report-path="))\n'
                           '    pathlib.Path(output).write_text("[]")\n')
        scanner.chmod(0o755)
        return root, scanner

    def test_real_clean_detached_git_scan_includes_head_and_preserves_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root, scanner = self.fixture(directory)
            report = history.scan(root, str(scanner), Path(directory) / "report")
            self.assertTrue(report["passed"])
            self.assertEqual(2, report["commits"])
            self.assertFalse(report["non_git_data_reviewed"])
            self.assertFalse(report["public_visibility_authorized"])
            self.assertNotIn("private", json.dumps(report["findings"]))

    def test_dirty_and_shallow_inputs_are_not_reported_as_scanned(self):
        with tempfile.TemporaryDirectory() as directory:
            root, scanner = self.fixture(directory)
            (root / "uncommitted").write_text("not covered")
            with self.assertRaisesRegex(ValueError, "clean checkout"):
                history.scan(root, str(scanner), Path(directory) / "report")
            (root / "uncommitted").unlink()
            head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, text=True, capture_output=True, check=True).stdout
            (root / ".git/shallow").write_text(head)
            with self.assertRaisesRegex(ValueError, "shallow"):
                history.scan(root, str(scanner), Path(directory) / "report")


if __name__ == "__main__":
    unittest.main()
