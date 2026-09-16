"""Contract identities from the repository's one authored version manifest.

Schemas and the example policy contain generated projections. Run
``python scripts/generate_contracts.py`` after deliberately changing the manifest.
This module belongs to the local reference runtime, not the portable core wheel.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
from types import MappingProxyType


CONTRACT_FIELDS = (
    "reference_contract", "core_contract", "verification_profile", "runtime_profile",
)


def read_contract_set(path: Path) -> dict:
    value = json.loads(path.read_text())
    if (not isinstance(value, dict) or set(value) != {"schema", *CONTRACT_FIELDS}
            or type(value["schema"]) is not int or value["schema"] != 1):
        raise ValueError(f"{path}: invalid contract-set manifest structure")
    for name in CONTRACT_FIELDS:
        if (not isinstance(value[name], str)
                or re.fullmatch(r"[a-z][a-z0-9-]*/v[1-9][0-9]*", value[name]) is None):
            raise ValueError(f"{path}: invalid contract identity {name}")
    return value


CONTRACT_SET = MappingProxyType(read_contract_set(
    Path(__file__).resolve().parents[1] / "config" / "contract-set.json"
))
REFERENCE_CONTRACT = CONTRACT_SET["reference_contract"]
CORE_CONTRACT = CONTRACT_SET["core_contract"]
VERIFICATION_PROFILE = CONTRACT_SET["verification_profile"]
RUNTIME_PROFILE = CONTRACT_SET["runtime_profile"]
