"""Portable decisions for autonomous-control-plane/v1; no provider side effects."""

from .decisions import (CoreError, completion_transition, goal_projection,
                        merge_authority, path_allowed, require_merge_identity,
                        require_revision_identity, risk_rank, trusted_checks_pass)

__version__ = "1.2.0"
CONTRACT = "autonomous-control-plane/v1"

__all__ = ["CoreError", "CONTRACT", "completion_transition", "goal_projection",
           "merge_authority", "path_allowed", "require_merge_identity",
           "require_revision_identity", "risk_rank", "trusted_checks_pass"]
