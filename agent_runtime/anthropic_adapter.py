"""Opt-in Anthropic Messages command/v2 adapter. One HTTP attempt, no fallback.

Structured output uses forced tool use (tool_choice pinned to one declared
tool), not a text-based JSON mode: the Messages API has no equivalent of
OpenAI's response_format=json_object. The controller still strictly validates
the returned role contract; this adapter only has to produce well-formed JSON
through the tool's input, not a semantically correct one.

Prompt caching here uses explicit cache_control breakpoints (see
agent_runtime/prompts.py:anthropic_messages), because the Messages API caches
only what is explicitly marked, unlike automatic prefix caching elsewhere.
This targets the documented Messages API request/response shape and does not
send an anthropic-beta header; verify header/field names against the current
API reference for your account before relying on this in production, and run
`agent-verify-adapter --live` against it first.
"""
import argparse
import os
import re
import sys
from urllib import error, parse, request

from .io import Closed, canonical, loads
from .usage import validate_usage
from .prompts import anthropic_messages
from control_plane_core import compact_prompt_schema

ANTHROPIC_VERSION = "2023-06-01"
TOOL_NAME = "submit_role_result"


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise Closed("Provider redirects are forbidden")


def endpoint(value):
    parsed = parse.urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment):
        raise Closed("Provider endpoint must be an explicit HTTPS URL without credentials, query or fragment")
    return value


def _usage(raw_usage):
    usage = {}
    if isinstance(raw_usage.get("output_tokens"), int):
        usage["output_tokens"] = raw_usage["output_tokens"]
    if isinstance(raw_usage.get("input_tokens"), int):
        # Anthropic reports cache reads/writes as counters separate from (not a
        # subset of) input_tokens; sum them so cached_input_tokens stays a true
        # subset of input_tokens, matching this runtime's usage contract.
        cached = raw_usage.get("cache_read_input_tokens")
        created = raw_usage.get("cache_creation_input_tokens")
        usage["input_tokens"] = (raw_usage["input_tokens"]
            + (created if isinstance(created, int) else 0)
            + (cached if isinstance(cached, int) else 0))
        if isinstance(cached, int):
            usage["cached_input_tokens"] = cached
    return validate_usage(usage)


def complete(envelope, *, url, key, timeout, max_tokens, opener=None):
    if (not isinstance(envelope, dict) or envelope.get("schema") != "command-reasoning/v2"
            or not isinstance(envelope.get("model"), str) or not envelope["model"]):
        raise Closed("Command/v2 request requires an operator-selected model")
    if not isinstance(envelope.get("effect_id"), str) or not re.fullmatch(r"[0-9a-f]{64}", envelope["effect_id"]):
        raise Closed("Command/v2 request requires a valid effect identity")
    layout = anthropic_messages(envelope)
    body = {"model": envelope["model"], "max_tokens": max_tokens, "stream": False,
            "system": layout["system"], "messages": layout["messages"],
            "tools": [{"name": TOOL_NAME, "description": "Submit the structured role result.",
                       "input_schema": compact_prompt_schema(envelope["output_schema"])}],
            "tool_choice": {"type": "tool", "name": TOOL_NAME}}
    req = request.Request(endpoint(url), data=canonical(body), method="POST", headers={
        "x-api-key": key, "anthropic-version": ANTHROPIC_VERSION, "content-type": "application/json",
        "X-Client-Request-Id": envelope.get("effect_id", ""), "User-Agent": "agent-control-command-v2"})
    transport = opener or request.build_opener(request.ProxyHandler({}), NoRedirect())
    with transport.open(req, timeout=timeout) as response:
        data = response.read(2_000_001)
    if len(data) > 2_000_000:
        raise Closed("Provider response exceeds byte limit")
    value = loads(data)
    usage = _usage(value.get("usage") or {})
    result = {}
    blocks = value.get("content")
    if value.get("stop_reason") == "tool_use" and isinstance(blocks, list):
        uses = [b for b in blocks if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") == TOOL_NAME]
        if len(uses) == 1 and isinstance(uses[0].get("input"), dict):
            result = uses[0]["input"]
    # Finished but invalid/truncated/refused answers are recorded by the
    # controller's bounded protocol repair path, with usage when available.
    return {"schema": "command-reasoning/v2", "result": result if isinstance(result, dict) else {},
            "usage": usage, "provider": {"id": "anthropic-messages", "model": envelope["model"],
                "request_id": str(value.get("id", ""))[:500]}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default="https://api.anthropic.com/v1/messages")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--max-output-tokens", type=int, default=8192)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    try:
        endpoint(args.endpoint)
        if not 1 <= args.timeout <= 7200 or not 1 <= args.max_output_tokens <= 1_000_000:
            raise Closed("Invalid provider bounds")
        key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not key or any(ord(c) < 33 or ord(c) == 127 for c in key):
            raise Closed("Missing or invalid provider credential")
        data = sys.stdin.buffer.read(2_000_001)
        if len(data) > 2_000_000:
            raise Closed("Provider request exceeds byte limit")
        envelope = loads(data)
        if args.check:
            if envelope.get("schema") != "command-reasoning/check/v1" or not envelope.get("model"):
                raise Closed("Readiness requires a model and the check protocol")
            value = {"schema": "command-reasoning/check/v1", "ready": True, "protocol": 2, "model_called": False}
        else:
            value = complete(envelope, url=args.endpoint, key=key, timeout=args.timeout, max_tokens=args.max_output_tokens)
        sys.stdout.buffer.write(canonical(value) + b"\n")
        return 0
    except (Closed, error.URLError, OSError, ValueError, KeyError, TypeError):
        print("Provider request failed; no automatic retry or billing fallback. Inspect the pending effect.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
