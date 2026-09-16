"""Bounded process I/O and durable controller-owned JSON; no product imports."""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import tempfile
import time


class Closed(RuntimeError):
    """A policy, identity or evidence gate is closed."""


class Unavailable(RuntimeError):
    """An external observation is temporarily unavailable; never infer success."""


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":")).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def loads(data):
    def unique(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise Closed("Duplicate JSON key")
            out[key] = value
        return out
    def invalid(_):
        raise Closed("Nonfinite JSON value")
    return json.loads(data, object_pairs_hook=unique, parse_constant=invalid)


def read_json(path, *, maximum=8_000_000):
    path = Path(path)
    if path.is_symlink() or path.stat().st_size > maximum:
        raise Closed("Expected bounded regular JSON")
    return loads(path.read_bytes())


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(canonical(value) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(name):
            os.unlink(name)


@contextlib.contextmanager
def locked(directory):
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (directory / "writer.lock").open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Closed("Another writer owns this run") from None
        yield


def run(argv, *, cwd=None, env=None, data=b"", timeout=60, limit=2_000_000, check=True):
    """Drain stdin/stdout/stderr concurrently, enforce bounds, kill descendants."""
    process = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               start_new_session=True)
    buffers = {"out": bytearray(), "err": bytearray()}
    incoming = memoryview(data)
    deadline = time.monotonic() + timeout
    with selectors.DefaultSelector() as selector:
        for stream, kind in ((process.stdout, "out"), (process.stderr, "err")):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, kind)
        if incoming:
            os.set_blocking(process.stdin.fileno(), False)
            selector.register(process.stdin, selectors.EVENT_WRITE, "in")
        else:
            process.stdin.close()
        try:
            while selector.get_map():
                if time.monotonic() >= deadline:
                    raise Unavailable("Process deadline exceeded: " + Path(argv[0]).name)
                for key, _ in selector.select(0.1):
                    stream, kind = key.fileobj, key.data
                    if kind == "in":
                        try:
                            incoming = incoming[os.write(stream.fileno(), incoming[:65536]):]
                        except BrokenPipeError:
                            incoming = memoryview(b"")
                        if not incoming:
                            selector.unregister(stream)
                            stream.close()
                    else:
                        chunk = os.read(stream.fileno(), 65536)
                        if not chunk:
                            selector.unregister(stream)
                            stream.close()
                        else:
                            buffers[kind].extend(chunk)
                            if sum(map(len, buffers.values())) > limit:
                                raise Closed("Process output exceeds limit")
            process.wait(timeout=max(0.1, deadline - time.monotonic()))
        except BaseException as exc:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
            if isinstance(exc, subprocess.TimeoutExpired):
                raise Unavailable("Process deadline exceeded: " + Path(argv[0]).name) from None
            raise
        finally:
            for stream in (process.stdin, process.stdout, process.stderr):
                if not stream.closed:
                    stream.close()
    result = subprocess.CompletedProcess(argv, process.returncode, bytes(buffers["out"]), bytes(buffers["err"]))
    if check and result.returncode:
        raise Closed(f"{Path(argv[0]).name} exited {result.returncode}; raw output is not public evidence")
    return result


def isolated_environment(home):
    result = {key: os.environ[key] for key in
              ("PATH", "LANG", "LC_ALL", "SSL_CERT_FILE", "SSL_CERT_DIR") if key in os.environ}
    result.update(HOME=str(home), TMPDIR=str(home), NO_COLOR="1")
    return result
