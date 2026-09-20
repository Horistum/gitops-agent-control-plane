"""Recoverable bootstrap, confined to a controller-created staging directory."""
import os
from pathlib import Path
import re
import shutil
import uuid

from control_plane_core import fingerprint
from .git import GitRepository
from .io import Closed, atomic_json, read_json
from .store import runtime_fingerprint


def initialize(root, policy, goal):
    product = Path(policy["product"]).resolve()
    source = GitRepository(product, policy["base_branch"])
    expected = {"schema": 1, "product": str(product), "policy": policy, "goal": goal,
                "base": source.resolve(policy["base_branch"]), "runtime_hash": runtime_fingerprint()}
    marker = root / "initialization.json"
    if marker.exists():
        intent = read_json(marker)
        if {k: v for k, v in intent.items() if k != "run_id"} != expected:
            raise Closed("Interrupted initialization authority or product revision changed")
        if not re.fullmatch(r"[0-9a-f]{32}", intent.get("run_id", "")):
            raise Closed("Invalid initialization identity")
    else:
        if (root / "product.git").exists():
            raise Closed("Unowned run repository exists; inspect it before starting")
        intent = {**expected, "run_id": uuid.uuid4().hex}
        atomic_json(marker, intent)
    stage = root / ("bootstrap-" + intent["run_id"])
    ready = root / "initialization-ready.json"
    identity = fingerprint(intent)
    destination = root / "product.git"
    if not ready.exists():
        if destination.exists():
            raise Closed("Unverified run repository; initialization cannot overwrite it")
        if stage.exists():
            if stage.is_symlink() or (not (stage / "owner.json").exists() and any(stage.iterdir())):
                raise Closed("Initialization staging ownership differs")
            if (stage / "owner.json").exists() and read_json(stage / "owner.json") != {"identity": identity}:
                raise Closed("Initialization staging ownership differs")
            # Only the clone below our exact controller-owned staging marker.
            clone = stage / "product.git"
            if clone.is_symlink():
                raise Closed("Initialization staging clone cannot be a symlink")
            if clone.exists():
                shutil.rmtree(clone)
        else:
            stage.mkdir(mode=0o700)
        atomic_json(stage / "owner.json", {"identity": identity})
        GitRepository.initialize(product, stage / "product.git", policy)
        atomic_json(ready, {"identity": identity})
    if read_json(ready) != {"identity": identity}:
        raise Closed("Initialization completion identity differs")
    if not destination.exists():
        os.replace(stage / "product.git", destination)
        fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    if destination.is_symlink():
        raise Closed("Run repository cannot be a symlink")
    repo = GitRepository(destination, policy["base_branch"])
    if repo.resolve(policy["base_branch"]) != expected["base"]:
        raise Closed("Initialized product revision differs")
    return repo, intent["run_id"]
