"""Late-bound owner credentials. References are policy; values never are."""
from __future__ import annotations

import os
from pathlib import Path
import re
import tempfile

from .io import Closed, Unavailable, canonical, isolated_environment, loads, run

ENV_NAME = re.compile(r"[A-Z_][A-Z0-9_]*")
# A provider credential cannot change executable lookup, interpreter startup,
# identity, Git transport, proxy routing, or the isolation envelope.
RESERVED = {"PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "NO_COLOR", "ENV", "BASH_ENV",
            "SHELLOPTS", "IFS", "NODE_OPTIONS", "RUBYOPT", "PERL5OPT", "JAVA_TOOL_OPTIONS",
            "JDK_JAVA_OPTIONS", "GH_TOKEN", "GITHUB_TOKEN", "SSL_CERT_FILE", "SSL_CERT_DIR",
            "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"}


def validate_reference(reference):
    if not isinstance(reference, dict):
        raise Closed("Credential reference must be an object")
    if reference.get("kind") == "env":
        if (set(reference) != {"kind", "name"} or not isinstance(reference.get("name"), str)
                or not ENV_NAME.fullmatch(reference["name"])):
            raise Closed("Credential requires one environment variable name")
    elif reference.get("kind") == "command":
        if set(reference) != {"kind", "argv", "reference", "timeout"}:
            raise Closed("Credential broker requires argv, reference and timeout")
        argv = reference["argv"]
        if (not isinstance(argv, list) or not 1 <= len(argv) <= 64
                or any(not isinstance(a, str) or not a or "\0" in a or len(a) > 4000 for a in argv)
                or not Path(argv[0]).is_absolute()):
            raise Closed("Credential broker requires an absolute executable and bounded arguments")
        if (not isinstance(reference["reference"], str) or not 1 <= len(reference["reference"]) <= 1000
                or any(ord(c) < 32 for c in reference["reference"])):
            raise Closed("Credential broker requires a bounded opaque reference")
        if type(reference["timeout"]) is not int or not 1 <= reference["timeout"] <= 60:
            raise Closed("Credential broker timeout must be 1..60 seconds")
    else:
        raise Closed("Unknown credential source")


def validate_provider_credentials(configuration):
    credentials = configuration.get("credentials", {})
    if not isinstance(credentials, dict) or len(credentials) > 16:
        raise Closed("At most 16 explicit provider credentials are allowed")
    if credentials and configuration["kind"] != "command":
        raise Closed("Provider credentials are only supported by command reasoning")
    for target, reference in credentials.items():
        if (not isinstance(target, str) or not ENV_NAME.fullmatch(target) or target in RESERVED
                or not (target in {"API_KEY", "TOKEN", "SECRET"}
                    or target.endswith(("_API_KEY", "_TOKEN", "_SECRET", "_ACCESS_KEY_ID", "_SECRET_ACCESS_KEY")))
                or target.startswith(("GIT_", "SSH_", "CODEX_", "PYTHON", "LD_", "DYLD_"))):
            raise Closed("Credential target would change the provider isolation envelope")
        validate_reference(reference)


class CredentialResolver:
    """Resolve on every use so external rotation needs no policy rewrite."""

    def resolve(self, reference, *, purpose):
        validate_reference(reference)
        if reference["kind"] == "env":
            value = os.environ.get(reference["name"], "")
        else:
            try:
                with tempfile.TemporaryDirectory(prefix="agent-credential-") as directory:
                    result = run(reference["argv"], cwd=directory,
                        env=isolated_environment(directory), timeout=reference["timeout"],
                        limit=32_000, check=False,
                        data=canonical({"schema": 1, "reference": reference["reference"], "purpose": purpose}))
                if result.returncode:
                    raise Closed("Credential broker failed")
                output = loads(result.stdout)
                if not isinstance(output, dict) or set(output) != {"value"}:
                    raise Closed("Invalid credential broker response")
                value = output["value"]
            except Unavailable:
                raise Unavailable("Credential broker unavailable") from None
            except (Closed, ValueError, OSError):
                # Never expose broker stderr, stdout, values or parser snippets.
                raise Closed("Credential broker failed or returned an invalid response") from None
        if (not isinstance(value, str) or not 1 <= len(value) <= 16_384
                or any(ord(c) < 32 or ord(c) == 127 for c in value)):
            raise Closed("Credential is missing or invalid")
        return value

    def provider_environment(self, configuration):
        validate_provider_credentials(configuration)
        return {name: self.resolve(reference, purpose="reasoning:" + name)
                for name, reference in configuration.get("credentials", {}).items()}
