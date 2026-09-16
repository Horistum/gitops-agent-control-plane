#!/usr/bin/env python3
"""Project config/contract-set.json into published schemas and the example policy.

Only identity fields are generated; the rest of each document stays authored in
place. --check compares semantic JSON, allowing harmless formatting changes.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from reference_runtime.contract_ids import read_contract_set


def projections(root: Path) -> dict[Path, dict]:
    manifest = read_contract_set(root / "config" / "contract-set.json")
    paths = (
        "config/reference-policy.json", "schemas/contract-set.schema.json",
        "schemas/policy.schema.json", "schemas/control-loop.schema.json",
        "schemas/evidence.schema.json",
    )
    output = {root / path: json.loads((root / path).read_text()) for path in paths}
    policy = output[root / paths[0]]
    policy["reference_contract"] = manifest["reference_contract"]
    profiles = {
        "core": manifest["core_contract"],
        "verification": manifest["verification_profile"],
        "runtime": manifest["runtime_profile"],
    }
    policy["contracts"] = profiles
    contract_schema = output[root / paths[1]]["properties"]
    for key, value in manifest.items():
        contract_schema[key]["const"] = value
    policy_schema = output[root / paths[2]]["properties"]
    policy_schema["reference_contract"]["const"] = manifest["reference_contract"]
    for key, value in profiles.items():
        policy_schema["contracts"]["properties"][key]["const"] = value
    loop_schema = output[root / paths[3]]["properties"]
    for key in ("reference_contract", "core_contract"):
        loop_schema[key]["const"] = manifest[key]
    output[root / paths[4]]["properties"]["reference_contract"]["const"] = manifest["reference_contract"]
    return output


def drifted_projections(root: Path) -> list[Path]:
    drift = [path for path, value in projections(root).items()
             if json.dumps(json.loads(path.read_text()), sort_keys=True) != json.dumps(value, sort_keys=True)]
    drift += [path for path, content in text_projections(root).items()
              if not path.exists() or path.read_text() != content]
    return drift


def text_projections(root: Path) -> dict[Path, str]:
    manifest = read_contract_set(root / "config" / "contract-set.json")
    core = (root / "control_plane_core" / "__init__.py").read_text()
    core, count = re.subn(r"(?m)^CONTRACT = .+$", "CONTRACT = " + repr(manifest["core_contract"]), core)
    if count != 1:
        raise ValueError("Core needs exactly one generated literal CONTRACT assignment")
    readme = (root / "README.md").read_text()
    begin, end = "<!-- contracts:begin -->", "<!-- contracts:end -->"
    if readme.count(begin) != 1 or readme.count(end) != 1:
        raise ValueError("README needs exactly one generated contract block")
    before, remainder = readme.split(begin)
    _, after = remainder.split(end)
    rows = ["| Component | Contract |", "|---|---|"]
    rows += [f"| {name.replace('_', ' ')} | `{value}` |"
             for name, value in manifest.items() if name != "schema"]
    return {root / "control_plane_core" / "__init__.py": core,
            root / "README.md": before + begin + "\n" + "\n".join(rows) + "\n" + end + after}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="reject drift without writing")
    args = parser.parse_args(argv)
    if args.check:
        drift = drifted_projections(ROOT)
        if drift:
            print("contract projection drift: " + ", ".join(str(p.relative_to(ROOT)) for p in drift), file=sys.stderr)
            print("Run python scripts/generate_contracts.py after reviewing the manifest change.", file=sys.stderr)
            return 1
    else:
        for path, value in projections(ROOT).items():
            if json.dumps(json.loads(path.read_text()), sort_keys=True) != json.dumps(value, sort_keys=True):
                indent = 2 if path.parent.name == "config" else None
                options = {} if indent else {"separators": (",", ":")}
                path.write_text(json.dumps(value, indent=indent, **options) + "\n")
        for path, content in text_projections(ROOT).items():
            path.write_text(content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
