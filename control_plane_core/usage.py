"""Pure, bounded provider token-usage validation shared by every consumer.

Moved out of agent_runtime so Flow and other consumers apply the identical
accounting rule instead of reimplementing it against their own receipts.
"""
from __future__ import annotations

from .decisions import CoreError

__all__ = ["TOKEN_FIELDS", "validate_usage"]

TOKEN_FIELDS = ("input_tokens", "output_tokens", "cached_input_tokens")


def validate_usage(value):
    """Bounded nonnegative token counters; cached tokens are a subset of input.

    Missing counters are unknown, not zero: an adapter that reports nothing
    supplies ``{}``. A nonempty but malformed report must fail closed rather
    than silently becoming a free/zero-cost observation.
    """
    if not isinstance(value, dict) or set(value) - set(TOKEN_FIELDS):
        raise CoreError("Usage must contain only supported token counters")
    if any(type(v) is not int or not 0 <= v <= 10**12 for v in value.values()):
        raise CoreError("Usage counters must be bounded nonnegative integers")
    if "cached_input_tokens" in value and ("input_tokens" not in value
            or value["cached_input_tokens"] > value["input_tokens"]):
        raise CoreError("Cached tokens must be a subset of reported input tokens")
    return dict(value)
