"""Real data-only reasoning transports. Fixture producers live only in tests."""
from __future__ import annotations

from pathlib import Path
import json
import shutil
import tempfile
from control_plane_core.schema import SchemaValidationError, validate_instance
from .contracts import ROLE_SCHEMAS, PROVIDER_RESPONSE_SCHEMA, normalize_role_output
from .credentials import CredentialResolver, validate_provider_credentials
from .io import Closed, InvalidJSON, Unavailable, canonical, isolated_environment, loads, read_json, run
from .usage import validate_usage
from .prompts import SHARED_INSTRUCTIONS, codex_request

ROLE_INSTRUCTIONS = {
    "discovery": "Choose exactly one eligible item. Do not invent scope or completion.",
    "architect": "Plan concrete changes. List exact working_set paths, invariants and verification steps.",
    "test_design": "Design independent executable scenarios for every test criterion before implementation.",
    "chief_plan": "Assess the plan, scope, test design and risks against the owner's goal. Reject gaps.",
    "developer": "Implement the bounded plan using complete file edits and exact prior content hashes.",
    "tester": "Add new independent executable tests. Never edit production or existing tests. Bind every test criterion to observed JUnit class:name identities. New-behavior tests must fail by assertion on base and pass on candidate; regression tests pass both.",
    "reviewer": "Review the actual changed files and observed test results. Identify concrete defects; do not rubber-stamp previous roles.",
    "challenge_review": "Independently challenge assumptions, missed edge cases and evidence quality in the actual diff.",
    "architect_accept": "Compare implemented changes with the approved architecture and all current acceptance obligations.",
    "chief_accept": "Assess the complete candidate against the bounded goal and staged evidence. Future CI/delivery evidence must remain deferred.",
}


class Reasoning:
    def __init__(self, configuration, *, credentials=None):
        self.config = configuration
        self.credentials = credentials or CredentialResolver()
        self._prepared_environment = None

    def prepare(self):
        """Local/broker preparation only; no model dispatch or persisted secrets."""
        self._prepared_environment = None
        if not shutil.which(self.config["argv"][0]):
            raise Unavailable("Reasoning executable is unavailable before dispatch")
        if self.config["kind"] == "command":
            try:
                self._prepared_environment = self.credentials.provider_environment(self.config)
            except (Closed, Unavailable, OSError):
                raise Unavailable("Reasoning credentials unavailable before dispatch") from None

    def discard_preparation(self):
        self._prepared_environment = None

    def preflight(self, *, readiness=False):
        validate_provider_credentials(self.config)
        if not shutil.which(self.config["argv"][0]):
            raise Closed("Reasoning executable is unavailable")
        if self.config["kind"] != "codex":
            report = {"kind": "command", "protocol": self.config.get("protocol", 1),
                    "authentication": "not-checked", "model_called": False,
                    "credential_targets": sorted(self.config.get("credentials", {})),
                    "checks": {"executable": "passed", "credentials": "not_checked", "adapter": "not_checked"}}
            if readiness:
                with tempfile.TemporaryDirectory(prefix="agent-preflight-") as directory:
                    env = isolated_environment(directory)
                    env.update(self.credentials.provider_environment(self.config))
                    report["checks"]["credentials"] = "passed"
                    if self.config.get("check_argv"):
                        result = run(self.config["check_argv"], cwd=directory, env=env,
                            data=canonical({"schema": "command-reasoning/check/v1", "model": self.config["model"]}),
                            timeout=min(60, self.config["timeout"]), limit=32_000, check=False)
                        if result.returncode:
                            raise Closed("Provider adapter readiness check failed")
                        value = loads(result.stdout)
                        if value != {"schema": "command-reasoning/check/v1", "ready": True,
                                    "protocol": self.config.get("protocol", 1), "model_called": False}:
                            raise Closed("Invalid provider readiness handshake")
                        report["checks"]["adapter"] = "passed"
            return report
        help_text = run(self.config["argv"] + ["exec", "--help"], limit=200_000).stdout.decode()
        for flag in ("--ignore-user-config", "--ignore-rules", "--output-schema", "--ephemeral"):
            if flag not in help_text:
                raise Closed("Installed Codex lacks required capability: " + flag)
        report = {"kind": "codex", "capabilities": "verified", "model_called": False,
                  "authentication": "not-checked", "checks": {"adapter": "passed", "credentials": "not_checked"}}
        if readiness:
            with tempfile.TemporaryDirectory(prefix="agent-login-check-") as directory:
                env = isolated_environment(directory); env["CODEX_HOME"] = self.config["codex_home"]
                result = run(self.config["argv"] + ["login", "status"], env=env, cwd=directory, check=False, limit=32_000)
                if result.returncode:
                    raise Closed("Codex login readiness check failed")
                report["checks"]["credentials"] = "passed"
                report["authentication"] = "login-status-verified"
        return report

    def execute(self, payload):
        try:
            return self._execute(payload)
        except (InvalidJSON, SchemaValidationError, json.JSONDecodeError, UnicodeDecodeError):
            return {"protocol_error": "Provider response violates the JSON contract"}
        finally:
            self.discard_preparation()

    def _execute(self, payload):
        phase = payload["phase"]
        schema = ROLE_SCHEMAS[phase]
        instructions = SHARED_INSTRUCTIONS + "\n" + ROLE_INSTRUCTIONS[phase]
        with tempfile.TemporaryDirectory(prefix="agent-reasoning-") as directory:
            root = Path(directory)
            environment = isolated_environment(root)
            request = {"instructions": instructions, "input": payload, "output_schema": schema}
            provider = {}
            if self.config["kind"] == "command":
                environment.update(self._prepared_environment if self._prepared_environment is not None
                                   else self.credentials.provider_environment(self.config))
                if self.config.get("protocol", 1) == 2:
                    request.update(schema="command-reasoning/v2", model=self.config["model"],
                        shared_instructions=SHARED_INSTRUCTIONS,
                        effect_id=payload.get("effect_id"), response_schema={**PROVIDER_RESPONSE_SCHEMA,
                            "properties": {**PROVIDER_RESPONSE_SCHEMA["properties"], "result": schema}})
                result = run(self.config["argv"], cwd=root, env=environment, data=canonical(request),
                             timeout=self.config["timeout"], check=False)
                if result.returncode:
                    raise Unavailable("Reasoning command failed; no success inferred")
                value = loads(result.stdout)
                usage = {}
                if self.config.get("protocol", 1) == 2:
                    validate_instance(value, PROVIDER_RESPONSE_SCHEMA)
                    try:
                        usage = validate_usage(value["usage"])
                    except Closed:
                        return {"protocol_error": "Provider usage violates the token contract"}
                    provider, value = value["provider"], value["result"]
            else:
                environment["CODEX_HOME"] = self.config["codex_home"]
                schema_path, output_path = root / "schema.json", root / "result.json"
                schema_path.write_bytes(canonical(schema))
                argv = self.config["argv"] + ["exec", "--ignore-user-config", "--ignore-rules",
                    "--skip-git-repo-check", "--ephemeral", "--sandbox", "read-only", "--json",
                    "--output-schema", str(schema_path), "--output-last-message", str(output_path),
                    "-c", 'forced_login_method="chatgpt"', "-c", 'model_provider="openai"',
                    "-c", 'approval_policy="never"', "-c", "features.shell_tool=false",
                    "-c", "features.unified_exec=false", "-c", "features.multi_agent=false",
                    "-c", 'web_search="disabled"', "-c", "hide_agent_reasoning=true"]
                if self.config["model"]:
                    argv += ["--model", self.config["model"]]
                result = run(argv + ["-"], cwd=root, env=environment, data=codex_request(request),
                             timeout=self.config["timeout"], check=False)
                if result.returncode:
                    raise Unavailable("Codex failed or has no available ChatGPT quota; no API fallback")
                complete, usage = False, {}
                for line in result.stdout.splitlines():
                    event = loads(line)
                    kind = event.get("item", {}).get("type")
                    if kind in {"command_execution", "file_change", "mcp_tool_call", "web_search", "collab_tool_call"}:
                        raise Closed("Unexpected effect/tool in data-only Codex session")
                    if event.get("type") in {"error", "turn.failed"}:
                        raise Unavailable("Codex turn did not succeed")
                    if event.get("type") == "turn.completed":
                        complete, usage = True, event.get("usage", {})
                if not complete or not output_path.is_file():
                    raise Closed("Codex produced no completed structured turn")
                value = read_json(output_path)
        value = normalize_role_output(value)
        try:
            validate_instance(value, schema)
        except SchemaValidationError:
            return {"protocol_error": "Provider result violates the role contract",
                    "usage": usage, "provider": provider}
        return {"result": value, "usage": usage, "provider": provider}
