"""Quiescent, checksummed run export and paused restore to a fresh directory."""
import os
import hashlib
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
from zipfile import ZipFile, ZIP_STORED

from .io import Closed, canonical, digest, loads, locked
from .store import Store
from .usage import usage_report

MAX_BYTES = 4_000_000_000
ROOTS = {"state.json", "receipts", "product.git", "initialization.json", "initialization-ready.json"}


def backup(root, output):
    root, output = Path(root).resolve(), Path(output).absolute()
    if output.is_relative_to(root) or output.exists():
        raise Closed("Backup requires a new output file outside the run")
    with locked(root):
        store = Store(root)
        if not store.state["paused"] or store.state.get("pending") or store.state.get("owner_intent"):
            raise Closed("Backup requires a paused run without pending effects or owner intent")
        usage_report(store)
        files = [p for p in root.rglob("*") if p.relative_to(root).parts[0] in ROOTS]
        if any(p.is_symlink() or not (p.is_dir() or stat.S_ISREG(p.lstat().st_mode)) for p in files):
            raise Closed("Backup refuses symlinks and special files")
        files = sorted(p for p in files if p.is_file())
        if len(files) > 50_000 or sum(p.stat().st_size for p in files) > MAX_BYTES:
            raise Closed("Backup exceeds byte limit")
        output.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".agent-backup-", dir=output.parent)
        os.close(fd)
        try:
            manifest = {"schema": 1, "run_id": store.state["run_id"], "files": {}}
            with ZipFile(temporary, "w", compression=ZIP_STORED) as archive:
                for path in files:
                    name = path.relative_to(root).as_posix(); hasher = hashlib.sha256(); size = 0
                    with path.open("rb") as source, archive.open(name, "w", force_zip64=True) as target:
                        for chunk in iter(lambda: source.read(1_048_576), b""):
                            hasher.update(chunk); size += len(chunk); target.write(chunk)
                    manifest["files"][name] = {"sha256": hasher.hexdigest(), "bytes": size}
                archive.writestr("backup-manifest.json", canonical(manifest))
            with open(temporary, "rb") as stream: os.fsync(stream.fileno())
            os.link(temporary, output)  # No overwrite if another exporter won.
            directory = os.open(output.parent, os.O_RDONLY | os.O_DIRECTORY)
            try: os.fsync(directory)
            finally: os.close(directory)
        finally:
            os.unlink(temporary)
    return {"backup": str(output), "run_id": manifest["run_id"], "files": len(manifest["files"])}


def restore(archive_path, root):
    root = Path(root).absolute()
    if root.exists() or root.is_symlink():
        raise Closed("Restore requires a new run directory")
    root.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".agent-restore-", dir=root.parent))
    try:
        with ZipFile(archive_path) as archive:
            rows = archive.infolist(); names = [row.filename for row in rows]
            if len(names) > 50_001 or len(names) != len(set(names)) or sum(row.file_size for row in rows) > MAX_BYTES:
                raise Closed("Duplicate paths or oversized backup")
            if archive.getinfo("backup-manifest.json").file_size > 8_000_000:
                raise Closed("Backup manifest exceeds limit")
            manifest = loads(archive.read("backup-manifest.json"))
            if manifest.get("schema") != 1 or set(names) != set(manifest["files"]) | {"backup-manifest.json"}:
                raise Closed("Backup manifest does not match archive")
            for name, expected in manifest["files"].items():
                path = PurePosixPath(name)
                if (path.is_absolute() or path.as_posix() != name or ".." in path.parts or not path.parts
                        or path.parts[0] not in ROOTS or "\\" in name or "\0" in name):
                    raise Closed("Unsafe backup path")
                target = stage / name; target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                hasher = hashlib.sha256(); size = 0
                with archive.open(name) as source, target.open("xb") as stream:
                    os.chmod(target, 0o600)
                    for chunk in iter(lambda: source.read(1_048_576), b""):
                        hasher.update(chunk); size += len(chunk); stream.write(chunk)
                    stream.flush(); os.fsync(stream.fileno())
                if {"sha256": hasher.hexdigest(), "bytes": size} != expected:
                    raise Closed("Backup content checksum differs")
        store = Store(stage)
        if (store.state["run_id"] != manifest["run_id"] or not store.state["paused"]
                or store.state.get("pending") or store.state.get("owner_intent")):
            raise Closed("Backup is not a quiescent paused run")
        usage_report(store)
        from .git import GitRepository
        for name in ("refs/heads", "refs/tags", "objects/info", "objects/pack"):
            (stage / "product.git" / name).mkdir(parents=True, exist_ok=True, mode=0o700)
        GitRepository(stage / "product.git", store.state["policy"]["base_branch"]).text("fsck", "--full")
        for directory in sorted([stage, *(p for p in stage.rglob("*") if p.is_dir())],
                                key=lambda p: len(p.parts), reverse=True):
            fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
            try: os.fsync(fd)
            finally: os.close(fd)
        # The destination is never opened by an automatic worker here.
        if root.exists(): raise Closed("Restore target appeared during validation")
        os.rename(stage, root)
        fd = os.open(root.parent, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(fd)
        finally: os.close(fd)
        return {"restored": str(root), "run_id": store.state["run_id"], "paused": True}
    finally:
        if stage.exists(): shutil.rmtree(stage)
