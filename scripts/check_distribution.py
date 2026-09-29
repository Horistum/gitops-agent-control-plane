#!/usr/bin/env python3
"""Build sdist -> wheel -> clean installation without modifying the checkout.

Uses the declared setuptools backend already installed in the build interpreter.
No dependency installation or registry publication is performed by this script.
"""
from __future__ import annotations

import argparse
import configparser
from email.parser import BytesParser
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import venv
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PORTABLE_PACKAGES = ("control_plane_core", "agent_worker")
PACKAGES = PORTABLE_PACKAGES + ("agent_runtime", "reference_runtime")
PORTABLE_LOCK = "CONTROL-CORE.lock.json"
SOURCE_DIRS = PACKAGES + ("docs", "config", "schemas", "examples", "scripts", "tests", ".github", "validation")
LEGAL_FILES = ("LICENSE", "NOTICE", "TRADEMARKS.md")
IGNORED_DIRS = {".git", ".demo", ".state", ".runtime", ".publication", ".audit", ".venv", "__pycache__", "build", "dist"}
MAX_BYTES = 50_000_000
MAX_MEMBERS = 20_000


def require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def source_files(root: Path) -> dict[str, bytes]:
    """Select only release source roots, excluding generated/local state."""
    result: dict[str, bytes] = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if any(part in IGNORED_DIRS or part.endswith(".egg-info") for part in rel.parts):
            continue
        if len(rel.parts) == 1:
            selected = path.name in {"LICENSE", "NOTICE", "pyproject.toml", "MANIFEST.in", ".gitignore", PORTABLE_LOCK} or path.suffix == ".md" or path.name.startswith("requirements") and path.suffix == ".txt"
        else:
            selected = rel.parts[0] in SOURCE_DIRS
        if not selected:
            continue
        require(not path.is_symlink(), f"Release source symlink is not allowed: {rel}")
        if path.is_file():
            if path.suffix in {".pyc", ".pyo"}:
                continue
            require(not path.name.startswith(".env") or path.name == ".env.example", f"Environment file in release source: {rel}")
            require(path.suffix not in {".pem", ".key", ".p12", ".pfx"}, f"Credential-shaped file in release source: {rel}")
            result[rel.as_posix()] = path.read_bytes()
    require(bool(result), "No release source files found")
    return result


def member_path(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    require(bool(name) and not path.is_absolute() and ".." not in path.parts and "\\" not in name,
            "Unsafe archive member path")
    require(path.parts and ".git" not in path.parts, "Git metadata in distribution")
    return path


def read_sdist(path: Path) -> dict[str, bytes]:
    """Read only regular tar members after validating the entire inventory."""
    with tarfile.open(path, "r:gz") as archive:
        members = archive.getmembers()
        require(0 < len(members) <= MAX_MEMBERS, "Invalid source archive member count")
        roots, names, total = set(), set(), 0
        for member in members:
            parts = member_path(member.name)
            require(parts.as_posix() not in names, "Duplicate source archive member")
            names.add(parts.as_posix())
            roots.add(parts.parts[0])
            require(member.isdir() or member.isfile(), "Links and special source archive members are forbidden")
            total += member.size
            require(0 <= member.size <= MAX_BYTES and total <= MAX_BYTES, "Source archive exceeds size bound")
        require(len(roots) == 1, "Source archive must have one root")
        result = {}
        for member in members:
            if not member.isfile():
                continue
            relative = PurePosixPath(member.name).parts[1:]
            require(bool(relative), "A root file cannot be a source distribution")
            stream = archive.extractfile(member)
            require(stream is not None, "Source archive member is unreadable")
            result[PurePosixPath(*relative).as_posix()] = stream.read()
        return result


def read_wheel(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        require(0 < len(entries) <= MAX_MEMBERS, "Invalid wheel member count")
        names, total = set(), 0
        for entry in entries:
            name = member_path(entry.filename).as_posix()
            require(name not in names, "Duplicate wheel member")
            names.add(name)
            kind = stat.S_IFMT(entry.external_attr >> 16)
            require(kind in {0, stat.S_IFREG, stat.S_IFDIR}, "Links and special wheel members are forbidden")
            total += entry.file_size
            require(total <= MAX_BYTES, "Wheel exceeds size bound")
        return {entry.filename: archive.read(entry) for entry in entries if not entry.is_dir()}


def validate_portable_selection(expected: dict[str, bytes], version: str) -> None:
    """Require the distribution's complete portable selection to match its lock."""
    require(PORTABLE_LOCK in expected, "Release source is missing the portable lock")
    lock = json.loads(expected[PORTABLE_LOCK])
    require(isinstance(lock, dict) and lock.get("schema") == 2
            and lock.get("packages") == list(PORTABLE_PACKAGES)
            and lock.get("version") == version and isinstance(lock.get("files"), dict),
            "Distribution portable lock metadata differs from release selection")
    for name in lock["files"]:
        member_path(name)
    selected = {name: digest(data) for name, data in expected.items()
                if PurePosixPath(name).parts[0] in PORTABLE_PACKAGES}
    require(all(package + "/__init__.py" in selected for package in PORTABLE_PACKAGES),
            "Distribution must include core and worker packages")
    locked_packages = {name: value for name, value in lock["files"].items()
                       if PurePosixPath(name).parts[0] in PORTABLE_PACKAGES}
    require(selected == locked_packages, "Distribution portable package selection differs from its lock")
    for name, value in lock["files"].items():
        require(name in expected and digest(expected[name]) == value,
                "Distribution lost or changed locked portable source: " + name)


def validate_archives(sdist: Path, wheel: Path, expected: dict[str, bytes]) -> dict:
    source, installed = read_sdist(sdist), read_wheel(wheel)
    project = tomllib.loads(expected["pyproject.toml"].decode())["project"]
    validate_portable_selection(expected, project["version"])
    # Every selected source input, not just one importable module, must survive.
    for name, data in expected.items():
        require(source.get(name) == data, f"Source archive lost or changed release input: {name}")
    generated = {"PKG-INFO", "setup.cfg"}
    egg = project["name"].replace("-", "_") + ".egg-info/"
    generated.update(egg + name for name in ("PKG-INFO", "SOURCES.txt", "dependency_links.txt", "entry_points.txt", "top_level.txt"))
    require(not set(source) - set(expected) - generated, "Unexpected source archive content")
    metadata_paths = [name for name in installed if name.endswith(".dist-info/METADATA")]
    require(len(metadata_paths) == 1, "Wheel must have one metadata record")
    prefix = metadata_paths[0].rsplit("/", 1)[0]
    metadata = BytesParser().parsebytes(installed[metadata_paths[0]])
    require(metadata["Name"] == project["name"] and metadata["Version"] == project["version"], "Distribution name/version drift")
    require(metadata["License-Expression"] == "Apache-2.0", "Missing or incorrect SPDX license expression")
    require(metadata["Requires-Python"] == project["requires-python"], "Python requirement drift")
    require(not metadata.get_all("Requires-Dist"), "Unexpected runtime dependencies")
    require(metadata["Description-Content-Type"] == "text/markdown", "README content type missing")
    require(set(metadata.get_all("License-File", [])) == set(LEGAL_FILES), "License file metadata drift")
    for name in LEGAL_FILES:
        require(installed.get(f"{prefix}/licenses/{name}") == expected[name], f"Wheel lost or changed legal file: {name}")
    require(expected["README.md"].decode().strip() in metadata.get_payload(), "Wheel README is incomplete")
    allowed_wheel = {f"{prefix}/{name}" for name in ("METADATA", "WHEEL", "top_level.txt", "entry_points.txt", "RECORD")}
    allowed_wheel.update(f"{prefix}/licenses/{name}" for name in LEGAL_FILES)
    for name, data in expected.items():
        parts = PurePosixPath(name).parts
        if parts[0] in PACKAGES and (name.endswith(".py") or parts[0] in PORTABLE_PACKAGES and name.endswith((".md", ".json"))):
            allowed_wheel.add(name)
            require(installed.get(name) == data, f"Wheel lost or changed package file: {name}")
    require(not set(installed) - allowed_wheel, "Unexpected wheel content")
    entrypoints = configparser.ConfigParser()
    entrypoints.read_string(installed.get(f"{prefix}/entry_points.txt", b"").decode())
    require(entrypoints.has_section("console_scripts") and dict(entrypoints["console_scripts"]) == project["scripts"], "Console entry point drift")
    return {"version": project["version"], "source_files_checked": len(expected),
            "wheel_files_checked": len(installed), "legal_files": list(LEGAL_FILES)}


def clean_env(home: Path) -> dict[str, str]:
    result = {key: os.environ[key] for key in ("PATH", "SYSTEMROOT", "LANG", "LC_ALL", "TMPDIR") if key in os.environ}
    result.update(HOME=str(home), PYTHONNOUSERSITE="1", PIP_NO_INDEX="1",
                  PIP_DISABLE_PIP_VERSION_CHECK="1", PIP_CONFIG_FILE=os.devnull)
    return result


def run(argv: list[str], cwd: Path, env: dict[str, str], logs: list[str], timeout: int = 120) -> None:
    result = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
    logs.append("COMMAND " + json.dumps(argv) + "\n" + result.stdout + result.stderr)
    require(result.returncode == 0, f"Distribution command failed ({result.returncode}): {argv[0]} {argv[1] if len(argv) > 1 else ''}")


def check_distribution(root: Path, output: Path) -> dict:
    root, output = root.resolve(), output.resolve()
    require(output != root and root not in output.parents, "Write build evidence outside the checkout")
    require(not output.exists() or output.is_dir() and not any(output.iterdir()), "Output must be a new or empty directory")
    project = tomllib.loads((root / "pyproject.toml").read_text())
    require(project["build-system"]["build-backend"] == "setuptools.build_meta", "Unsupported build backend")
    backend_version = importlib.metadata.version("setuptools")
    require(int(backend_version.split(".")[0]) >= 77, "Install the declared setuptools>=77 build backend first")
    expected = source_files(root)
    validate_portable_selection(expected, project["project"]["version"])
    output.mkdir(parents=True, exist_ok=True)
    logs: list[str] = []
    try:
        with tempfile.TemporaryDirectory(prefix="publication-package-") as temporary:
            work = Path(temporary)
            snapshot, extracted = work / "source", work / "extracted"
            snapshot.mkdir(); extracted.mkdir()
            for name, data in expected.items():
                path = snapshot / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                path.chmod(0o755 if (root / name).stat().st_mode & 0o111 else 0o644)
            env = clean_env(work)
            run([sys.executable, "-S", "scripts/sync_control_core.py", "--check"], snapshot, env, logs)
            run([sys.executable, "-c", "from setuptools.build_meta import build_sdist; build_sdist(" + repr(str(output)) + ")"], snapshot, env, logs)
            sdists = list(output.glob("*.tar.gz"))
            require(len(sdists) == 1, "Expected exactly one source archive")
            source = read_sdist(sdists[0])
            for name, data in source.items():
                path = extracted / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            # Preserve authored executable bits for source-distribution checks.
            with tarfile.open(sdists[0], "r:gz") as archive:
                for member in archive.getmembers():
                    if member.isfile():
                        relative = PurePosixPath(*PurePosixPath(member.name).parts[1:])
                        (extracted / relative).chmod(0o755 if member.mode & 0o111 else 0o644)
            run([sys.executable, "-c", "from setuptools.build_meta import build_wheel; build_wheel(" + repr(str(output)) + ")"], extracted, env, logs)
            wheels = list(output.glob("*.whl"))
            require(len(wheels) == 1, "Expected exactly one wheel")
            result = validate_archives(sdists[0], wheels[0], expected)
            run([sys.executable, "-S", "scripts/sync_control_core.py", "--check"], extracted, env, logs)
            run([sys.executable, "-S", "scripts/check_publication.py"], extracted, env, logs)
            install = work / "venv"
            venv.EnvBuilder(with_pip=True).create(install)
            python = install / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            run([str(python), "-I", "-m", "pip", "install", "--no-index", "--no-deps", str(wheels[0])], work, env, logs)
            probe = ("import pathlib, control_plane_core, agent_worker, agent_runtime; "
                     "from agent_worker import AppServerWorker, SourceBroker; "
                     "from control_plane_core import technical_recovery, work_authorization, candidate_authorization; "
                     "assert control_plane_core.__version__ == "
                     + repr(result["version"]) + "; assert all(pathlib.Path(module.__file__).is_relative_to("
                     + repr(str(install)) + ") for module in (control_plane_core, agent_worker, agent_runtime))")
            run([str(python), "-I", "-c", probe], work, env, logs)
            for command in project["project"]["scripts"]:
                run([str(python.parent / command), "--help"], work, env, logs)
            run([str(python), "-I", "-m", "control_plane_core.conformance"], work, env, logs)
            result.update(passed=True, scope="sdist-wheel-clean-install", backend="setuptools.build_meta",
                          backend_version=backend_version, python=sys.version.split()[0],
                          source_inventory_sha256=digest(json.dumps({k: digest(v) for k, v in expected.items()}, sort_keys=True).encode()),
                          artifacts={p.name: digest(p.read_bytes()) for p in (sdists[0], wheels[0])},
                          checkout_unchanged=source_files(root) == expected,
                          live_provider_validation=False, publication_authorized=False)
            require(result["checkout_unchanged"], "Release source changed during the build check")
            (output / "distribution-report.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
            (output / "SHA256SUMS").write_text("".join(f"{value}  {name}\n" for name, value in sorted(result["artifacts"].items())))
            return result
    finally:
        (output / "build.log").write_text("\n".join(logs))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(check_distribution(ROOT, args.output), indent=2, sort_keys=True))
        return 0
    except (ValueError, OSError, subprocess.SubprocessError, importlib.metadata.PackageNotFoundError) as exc:
        print(f"Distribution check failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
