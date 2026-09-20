"""Opt-in Chat Completions command/v2 adapter. One HTTP attempt, no fallback."""
import argparse
import os
import sys
from urllib import error, parse, request

from .io import Closed, canonical, loads
from .usage import validate_usage


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise Closed("Provider redirects are forbidden")


def endpoint(value):
    parsed = parse.urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment):
        raise Closed("Provider endpoint must be an explicit HTTPS URL without credentials, query or fragment")
    return value


def complete(envelope, *, url, key, timeout, max_tokens, opener=None):
    if (not isinstance(envelope, dict) or envelope.get("schema") != "command-reasoning/v2"
            or not isinstance(envelope.get("model"), str) or not envelope["model"]):
        raise Closed("Command/v2 request requires an operator-selected model")
    body = {"model": envelope["model"], "store": False, "stream": False, "n": 1,
            "max_completion_tokens": max_tokens, "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": envelope["instructions"] +
                "\nReturn a JSON object matching this schema:\n" + canonical(envelope["output_schema"]).decode()},
                {"role": "user", "content": canonical(envelope["input"]).decode()}]}
    req = request.Request(endpoint(url), data=canonical(body), method="POST", headers={
        "Authorization": "Bearer " + key, "Content-Type": "application/json",
        "X-Client-Request-Id": envelope.get("effect_id", ""), "User-Agent": "agent-control-command-v2"})
    transport = opener or request.build_opener(request.ProxyHandler({}), NoRedirect())
    with transport.open(req, timeout=timeout) as response:
        data = response.read(2_000_001)
    if len(data) > 2_000_000:
        raise Closed("Provider response exceeds byte limit")
    value = loads(data)
    raw_usage = value.get("usage") or {}
    usage = {target: raw_usage[source] for source, target in
             (("prompt_tokens", "input_tokens"), ("completion_tokens", "output_tokens")) if source in raw_usage}
    details = raw_usage.get("prompt_tokens_details") or {}
    if "cached_tokens" in details:
        usage["cached_input_tokens"] = details["cached_tokens"]
    usage = validate_usage(usage)
    choices = value.get("choices", [])
    result = {}
    if len(choices) == 1:
        choice = choices[0]; message = choice.get("message", {})
        if (choice.get("finish_reason") == "stop" and not message.get("refusal")
                and not message.get("tool_calls") and not message.get("function_call")):
            try:
                result = loads(message["content"])
            except (Closed, ValueError, TypeError, KeyError):
                result = {}
    # Finished but invalid/truncated/refused answers are recorded by the
    # controller's bounded protocol repair path, with usage when available.
    return {"schema": "command-reasoning/v2", "result": result if isinstance(result, dict) else {},
            "usage": usage, "provider": {"id": "openai-chat-completions", "model": envelope["model"],
                "request_id": str(value.get("id", ""))[:500]}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default="https://api.openai.com/v1/chat/completions")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--max-output-tokens", type=int, default=8192)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    try:
        endpoint(args.endpoint)
        if not 1 <= args.timeout <= 7200 or not 1 <= args.max_output_tokens <= 1_000_000:
            raise Closed("Invalid provider bounds")
        key = os.environ.get("OPENAI_API_KEY", "")
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
