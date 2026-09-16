#!/usr/bin/env python3
"""Mandatory CI container integration; reasoning peer is explicitly a test fixture."""
import argparse
import json
from pathlib import Path
import sys
import tempfile
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
from agent_runtime.controller import Controller
from runtime_support import build_product, goal, policy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="agent-podman-integration-") as directory:
        root = Path(directory)
        product = root / "product"
        build_product(product)
        configuration = policy(product)
        configuration["execution"].update(kind="podman", image=args.image)
        controller = Controller.start(root / "state", configuration, goal())
        for _ in range(100):
            result = controller.tick()
            if result["status"] != "RUNNING":
                break
        print(json.dumps(result, indent=2))
        if result["status"] != "COMPLETED":
            # This script owns a disposable public test product; printing these
            # receipts is safe and makes real execution failures diagnosable.
            for path in sorted((controller.root / "receipts").glob("*.json")):
                receipt = json.loads(path.read_text())
                if receipt["request"]["kind"] == "verify":
                    print(json.dumps(receipt["output"], indent=2), flush=True)
            raise SystemExit("Real Podman lifecycle did not complete")
        evidence = controller.state["archive"][0]
        assert evidence["independent_baseline"]["junit"]["failed_identities"] == ["TASK1:test_value"]
        assert evidence["postmerge_evidence"]["passed"]
        print("Verified actual rootless Podman baseline, negative control, candidate and merge execution. Model transport: test protocol peer.")


if __name__ == "__main__":
    main()
