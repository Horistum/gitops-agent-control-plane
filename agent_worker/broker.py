"""Capability-based source access and reversible edit overlays; never a shell."""
from __future__ import annotations
import copy
import hashlib
import re
from .protocol import ToolInputError, WorkerError, canonical


def _object(properties):
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}

EDIT_SCHEMA = _object({"path": {"type": "string"}, "expected_sha256": {"type": "string"},
                       "delete": {"type": "boolean"}, "content": {"type": "string"}})
TOOLS = [
    {"type": "function", "name": "read_source", "description": "Read exact source or staged overlay. Paths are repository-relative; lines are inclusive.",
     "inputSchema": _object({"path": {"type": "string"}, "start_line": {"type": "integer", "minimum": 1},
                             "end_line": {"type": "integer", "minimum": 1}})},
    {"type": "function", "name": "search_source", "description": "Search exact committed source using one bounded literal. Returns paths; read needed excerpts next.",
     "inputSchema": _object({"literal": {"type": "string"}})},
    {"type": "function", "name": "stage_edits", "description": "Stage bounded full-file replacements/deletions against latest content hashes. Does not commit, execute or publish.",
     "inputSchema": _object({"edits": {"type": "array", "items": EDIT_SCHEMA}})},
]


def safe_path(value):
    if (not isinstance(value, str) or not value or value.startswith(("/", "\\")) or "\\" in value
            or any(ord(char) < 32 for char in value) or any(part in ("", ".", "..") for part in value.split("/"))
            or ":" in value):
        raise WorkerError("Worker source path must be a safe repository-relative path")
    return value

class SourceBroker:
    """Adapters provide exact-object reads/searches and immutable edit authorization.

    read(path) returns UTF-8 text with sha256, or {missing: True}. Authorization
    receives the complete resulting edit set, with hashes relative to the original
    controller head. The broker stores no filesystem content or credentials.
    """
    def __init__(self, read, search, authorize, *, writable=False, max_patch_bytes=250_000,
                 max_changed_files=32, max_read_bytes=250_000):
        self.read = read; self.search = search; self.authorize = authorize; self.writable = writable
        self.max_patch_bytes = max_patch_bytes; self.max_changed_files = max_changed_files; self.max_read_bytes = max_read_bytes
        self.original = {}; self.overlay = {}; self.tools = copy.deepcopy(TOOLS if writable else TOOLS[:2])

    def _original(self, path):
        if path not in self.original:
            value = self.read(path)
            if not isinstance(value, dict): raise WorkerError("Source adapter returned malformed source")
            if value.get("missing") is True:
                self.original[path] = None
            else:
                text = value.get("text")
                if not isinstance(text, str) or len(text.encode()) > 1_000_000 or "\0" in text:
                    raise WorkerError("Source is not bounded UTF-8 text")
                if hashlib.sha256(text.encode()).hexdigest() != value.get("sha256"):
                    raise WorkerError("Source adapter returned inconsistent content hash")
                self.original[path] = text
        return self.original[path]

    def _current(self, path):
        return self.overlay[path] if path in self.overlay else self._original(path)

    def call(self, name, arguments):
        if name not in {tool["name"] for tool in self.tools}: raise WorkerError("Worker tool is not authorized")
        if not isinstance(arguments, dict): raise ToolInputError("Worker tool arguments must be an object")
        expected = {"read_source": {"path", "start_line", "end_line"}, "search_source": {"literal"},
                    "stage_edits": {"edits"}}[name]
        if set(arguments) != expected: raise ToolInputError("Worker tool argument fields differ from contract")
        if name == "read_source":
            path = safe_path(arguments["path"]); start = arguments["start_line"]; end = arguments["end_line"]
            if type(start) is not int or type(end) is not int or start < 1 or end < start or end - start > 500:
                raise ToolInputError("Worker source excerpt must contain 1 to 501 ordered lines")
            text = self._current(path)
            if text is None: return {"path": path, "missing": True, "sha256": "absent"}
            lines = text.splitlines(keepends=True); selected = "".join(lines[start - 1:end])
            bounded = selected.encode()[:self.max_read_bytes].decode(errors="ignore")
            return {"path": path, "sha256": hashlib.sha256(text.encode()).hexdigest(), "text": bounded,
                    "line_start": start, "line_end": start + len(bounded.splitlines()) - 1,
                    "total_lines": len(lines), "truncated": len(bounded) != len(selected), "staged": path in self.overlay}
        if name == "search_source":
            literal = arguments["literal"]
            if not isinstance(literal, str) or not 2 <= len(literal) <= 120 or any(ord(c) < 32 for c in literal):
                raise ToolInputError("Worker search must be a bounded literal")
            value = self.search(literal)
            if len(canonical(value)) > self.max_read_bytes: raise WorkerError("Worker search response exceeds bound")
            return value
        edits = arguments["edits"]
        staged = self._validate_edits(edits, self.overlay)
        proposed = self._edits(staged)
        self.authorize(copy.deepcopy(proposed))
        self.overlay = staged
        return {"staged": [{"path": edit["path"], "sha256": "absent" if edit["delete"] else
                  hashlib.sha256(edit["content"].encode()).hexdigest()} for edit in edits],
                "changed_files": len(proposed), "patch_bytes": sum(len(e["content"].encode()) for e in proposed)}

    def _validate_edits(self, edits, overlay):
        """Validate either ingress before authorization or changing the overlay."""
        if not self.writable:
            raise WorkerError("Read-only worker attempted edits")
        if not isinstance(edits, list) or not 1 <= len(edits) <= self.max_changed_files:
            raise WorkerError("Worker edit batch is empty or oversized")
        staged = dict(overlay); seen = set()
        for edit in edits:
            if not isinstance(edit, dict) or set(edit) != {"path", "expected_sha256", "delete", "content"}:
                raise ToolInputError("Malformed worker edit")
            path = safe_path(edit["path"])
            if path in seen: raise ToolInputError("Duplicate worker edit path")
            seen.add(path); old = overlay[path] if path in overlay else self._original(path)
            expected_hash = hashlib.sha256(old.encode()).hexdigest() if old is not None else "absent"
            if edit["expected_sha256"] != expected_hash: raise ToolInputError("Worker edit precondition failed")
            if type(edit["delete"]) is not bool or not isinstance(edit["content"], str) or "\0" in edit["content"]:
                raise ToolInputError("Worker edits require text and an explicit deletion boolean")
            if edit["delete"] and (old is None or edit["content"]): raise ToolInputError("Invalid worker deletion")
            replacement = None if edit["delete"] else edit["content"]
            if replacement == old: raise ToolInputError("Worker edit makes no change")
            staged[path] = replacement
        proposed = self._edits(staged)
        if not proposed or len(proposed) > self.max_changed_files or sum(len(e["content"].encode()) for e in proposed) > self.max_patch_bytes:
            raise WorkerError("Worker cumulative patch bound exceeded or net patch is empty")
        return staged

    def _edits(self, overlay=None):
        edits = []
        for path, content in sorted((self.overlay if overlay is None else overlay).items()):
            old = self._original(path)
            if content == old: continue
            edits.append({"path": path, "expected_sha256": "absent" if old is None else hashlib.sha256(old.encode()).hexdigest(),
                          "delete": content is None, "content": content or ""})
        return edits

    def finalize(self, result):
        if not isinstance(result, dict): raise WorkerError("Worker final result must be an object")
        result = copy.deepcopy(result); staged = self._edits()
        edits = result.get("edits", [])
        if not isinstance(edits, list): raise WorkerError("Worker final edits must be an array")
        if edits:
            edits = self._edits(self._validate_edits(edits, {}))
        if staged:
            if edits and edits != staged:
                raise WorkerError("Final result contradicts staged worker edits")
            if result.get("verdict") != "ready": raise WorkerError("Staged edits require a ready final proposal")
            edits = staged
        if edits:
            if result.get("verdict") != "ready": raise WorkerError("Edits require a ready final proposal")
            self.authorize(copy.deepcopy(edits))
            result["edits"] = edits
        return result
