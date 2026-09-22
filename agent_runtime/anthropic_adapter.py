"""Opt-in Anthropic Messages command/v2 adapter. One HTTP attempt, no fallback.

Structured output uses the native output_config.format=json_schema mechanism
(stable, no anthropic-beta header required), not forced tool use. This
project's own role schemas (agent_runtime/contracts.py's text()/array()
helpers) use minLength/maxLength/maxItems bounds on nearly every field, and
Anthropic's structured-output schema compiler rejects those outright with a
400 if sent as-is: its documented supported keyword set is limited to
type/properties/required/enum/const/$ref/$def/anyOf/allOf/format/items plus
additionalProperties=false; minLength, maxLength, minimum, maximum,
multipleOf and maxItems are explicitly unsupported, and minItems accepts only
0 or 1. The official SDKs paper over this by stripping those keywords
client-side before the request (folding each into the field's description
instead) and then validating the real response against the original,
unstripped schema themselves. This raw-HTTP adapter has no SDK to do that, so
_strict_output_schema() below performs the same transformation by hand. The
controller still re-validates every returned role result against the
original, unstripped envelope["output_schema"] regardless of what the
provider enforced during generation, so this stripping only loosens
generation-time constraints; it never changes what is accepted as a final
answer.

Prompt caching here uses explicit cache_control breakpoints (see
agent_runtime/prompts.py:anthropic_messages), because the Messages API caches
only what is explicitly marked, unlike automatic prefix caching elsewhere.
"""
import argparse
import copy
import os
import re
import sys
from urllib import error, parse, request

from .io import Closed, canonical, loads
from .usage import validate_usage
from .prompts import anthropic_messages

ANTHROPIC_VERSION = "2023-06-01"
# Keywords not in Anthropic's documented structured-output support list
# (platform.claude.com/docs/en/build-with-claude/structured-outputs); sending
# any of these causes a 400, so they are stripped, never enforced by the
# provider. minItems is separate below because 0 and 1 remain valid.
_UNSUPPORTED_SCHEMA_KEYWORDS = (
    "minLength", "maxLength", "minimum", "maximum", "multipleOf",
    "maxItems", "minProperties", "maxProperties")


def _strict_output_schema(schema):
    """Strip JSON Schema keywords Anthropic's output_config compiler 400s on,
    folding each into the field description as a hint instead of an enforced
    bound. Never use the result as anything but a generation-time hint: the
    original schema stays the sole validation authority."""
    if not isinstance(schema, dict):
        return copy.deepcopy(schema)
    result = copy.deepcopy(schema)
    hints = []
    for keyword in _UNSUPPORTED_SCHEMA_KEYWORDS:
        if keyword in result:
            value = result.pop(keyword)
            # A zero lower bound is the schema-implied default (as compact_prompt_schema
            # already treats it elsewhere); noting it would just spend tokens for nothing.
            if keyword in ("minLength", "minProperties") and value == 0:
                continue
            hints.append(f"{keyword}={value}")
    if isinstance(result.get("minItems"), int) and result["minItems"] not in (0, 1):
        hints.append(f"minItems={result.pop('minItems')}")
    if hints:
        note = "Not enforced at generation time, only checked after: " + ", ".join(hints)
        result["description"] = (result.get("description", "").rstrip() + " " + note).strip()
    if result.get("type") == "object" and isinstance(result.get("properties"), dict):
        result["additionalProperties"] = False
        result["properties"] = {name: _strict_output_schema(value) for name, value in result["properties"].items()}
    for key in ("$defs", "definitions", "patternProperties"):
        if isinstance(result.get(key), dict):
            result[key] = {name: _strict_output_schema(value) for name, value in result[key].items()}
    if isinstance(result.get("items"), dict):
        result["items"] = _strict_output_schema(result["items"])
    for key in ("allOf", "anyOf", "prefixItems"):
        if isinstance(result.get(key), list):
            result[key] = [_strict_output_schema(value) for value in result[key]]
    return result


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
            "output_config": {"format": {"type": "json_schema",
                "schema": _strict_output_schema(envelope["output_schema"])}}}
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
    # output_config.format guarantees a well-formed JSON text block on a clean
    # end_turn; any other stop_reason (max_tokens, refusal, ...) means an
    # incomplete or unusable answer, left as result={} for the controller's
    # bounded protocol repair path rather than parsed as if it were real.
    if value.get("stop_reason") == "end_turn" and isinstance(blocks, list):
        texts = [b["text"] for b in blocks if isinstance(b, dict) and b.get("type") == "text"
                 and isinstance(b.get("text"), str)]
        if len(texts) == 1:
            try:
                result = loads(texts[0])
            except (Closed, ValueError, TypeError, KeyError):
                result = {}
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
