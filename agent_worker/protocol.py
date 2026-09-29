"""Bounded local records shared by worker transports and source brokers."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import contextlib
import fcntl
import stat

PROFILE = "codex-app-server-broker/v1"

class WorkerError(RuntimeError):
    """The worker cannot establish the configured capability or authority."""

class ToolInputError(WorkerError):
    """A bounded, correctable argument error with no applied source effect."""

class WorkerIndeterminate(WorkerError):
    """A dispatched turn has no trustworthy completed result; never auto-repeat it."""

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()

def fingerprint(value):
    return hashlib.sha256(canonical(value)).hexdigest()

@contextlib.contextmanager
def exclusive_lock(path: Path):
    """Open the exact owner-controlled regular file without following symlinks."""
    path = Path(path).absolute()
    directory = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY)
    descriptor = None
    try:
        for part in path.parts[1:-1]:
            next_directory = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory); directory = next_directory
        descriptor = os.open(path.name, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
                             0o600, dir_fd=directory)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid() or metadata.st_nlink != 1:
            raise WorkerError("Worker lock must be an owner-owned regular file with one link")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise WorkerError("Another worker owns this session or commissioning lock") from exc
        yield
    except OSError as exc:
        raise WorkerError("Worker lock path is unavailable or unsafe") from exc
    finally:
        if descriptor is not None: os.close(descriptor)
        os.close(directory)

def source_identity(root, paths):
    """Bind reviewed adapter authority code without including local configuration."""
    root = Path(root)
    return fingerprint({name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in sorted(paths)})

def loads(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise WorkerError("Duplicate JSON key in worker protocol")
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(WorkerError("Non-finite JSON value")))
    except (ValueError, UnicodeError) as exc:
        raise WorkerError("Invalid worker JSON") from exc

def atomic(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink() or path.parent.is_symlink():
        raise WorkerError("Worker record path must not be a symlink")
    temporary = path.with_suffix(".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(canonical(value)); stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, path)
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)

def read_record(path: Path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 4_000_000:
        raise WorkerError("Invalid or oversized worker record")
    return loads(path.read_bytes())

def validate_profile(profile):
    if not isinstance(profile, dict) or profile.get("profile") != PROFILE or profile.get("experimental") is not True:
        raise WorkerError("Worker requires explicit experimental codex-app-server-broker/v1 profile")
    required = {"profile", "experimental", "codex_version", "schema_sha256", "max_tool_calls", "max_tool_bytes",
                "max_frame_bytes", "max_output_bytes", "timeout_seconds", "smoke_attestation"}
    if set(profile) != required:
        raise WorkerError("Worker profile fields are incomplete or unknown")
    if not isinstance(profile["codex_version"], str) or not profile["codex_version"].strip():
        raise WorkerError("Worker Codex version must be pinned")
    if not isinstance(profile["schema_sha256"], str) or not re.fullmatch("[0-9a-f]{64}", profile["schema_sha256"]):
        raise WorkerError("Worker generated schema must be pinned by SHA256")
    bounds = {"max_tool_calls": (1, 128), "max_tool_bytes": (1024, 4_000_000),
              "max_frame_bytes": (1024, 2_000_000), "max_output_bytes": (4096, 16_000_000),
              "timeout_seconds": (1, 3600)}
    for key, (minimum, maximum) in bounds.items():
        if type(profile[key]) is not int or not minimum <= profile[key] <= maximum:
            raise WorkerError("Invalid worker bound: " + key)
    if profile["max_frame_bytes"] > profile["max_output_bytes"]:
        raise WorkerError("Worker frame bound exceeds output bound")
    if not isinstance(profile["smoke_attestation"], str) or not Path(profile["smoke_attestation"]).is_absolute():
        raise WorkerError("Worker smoke attestation must be an absolute owner-managed path")
    return dict(profile)

PROFILE_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "profile": {"type": "string", "const": PROFILE}, "experimental": {"type": "boolean", "const": True},
        "codex_version": {"type": "string", "minLength": 1, "maxLength": 200},
        "schema_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "max_tool_calls": {"type": "integer", "minimum": 1, "maximum": 128},
        "max_tool_bytes": {"type": "integer", "minimum": 1024, "maximum": 4_000_000},
        "max_frame_bytes": {"type": "integer", "minimum": 1024, "maximum": 2_000_000},
        "max_output_bytes": {"type": "integer", "minimum": 4096, "maximum": 16_000_000},
        "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 3600},
        "smoke_attestation": {"type": "string", "minLength": 1, "maxLength": 4000},
    },
    "required": ["profile", "experimental", "codex_version", "schema_sha256", "max_tool_calls", "max_tool_bytes",
                 "max_frame_bytes", "max_output_bytes", "timeout_seconds", "smoke_attestation"],
}
