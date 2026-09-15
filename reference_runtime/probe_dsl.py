from __future__ import annotations

try:
    from .probe_dsl_v7 import *  # noqa: F401,F403
except ImportError:  # standalone probe worker import path
    from probe_dsl_v7 import *  # type: ignore # noqa: F401,F403
