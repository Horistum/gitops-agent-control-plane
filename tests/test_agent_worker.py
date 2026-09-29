"""Controlled subprocess tests of the sustained worker boundary, without providers."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from agent_worker import AppServerWorker, SourceBroker, WorkerError, WorkerIndeterminate
from agent_worker.capabilities import inspect_cli
from agent_worker.protocol import atomic, exclusive_lock, fingerprint, source_identity

FIXTURE = Path(__file__).parent / "fixtures" / "worker_app_server.py"
SCHEMA = {"type": "object", "properties": {"verdict": {"type": "string", "enum": ["ready"]},
    "edits": {"type": "array", "items": {"type": "object"}}}, "required": ["verdict", "edits"], "additionalProperties": False}

class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup); self.root = Path(self.temp.name)
        self.argv = [sys.executable, str(FIXTURE)]
        report = inspect_cli(self.argv)
        self.profile = {"profile": "codex-app-server-broker/v1", "experimental": True,
            "codex_version": report["codex_version"], "schema_sha256": report["schema_sha256"],
            "max_tool_calls": 8, "max_tool_bytes": 100_000, "max_frame_bytes": 100_000,
            "max_output_bytes": 1_000_000, "timeout_seconds": 5,
            "smoke_attestation": str(self.root / "smoke.json")}
        self.authorized = []

    def worker(self, scenario="normal"):
        worker = AppServerWorker(self.profile, self.root / "home", self.root / "workers",
                                argv=self.argv + ["--scenario", scenario])
        # This deliberately controlled local record only exercises the gate; it
        # must never be presented as target-host live smoke evidence.
        atomic(Path(self.profile["smoke_attestation"]), {"identity": worker.smoke_identity(), "passed": True, "model_called": True})
        return worker

    def broker(self, writable=True):
        def read(path):
            if path != "src/service.py": return {"missing": True}
            return {"text": "value = 1\n", "sha256": hashlib.sha256(b"value = 1\n").hexdigest()}
        def authorize(edits):
            if any(edit["path"] != "src/service.py" for edit in edits): raise WorkerError("Outside concrete working set")
            self.authorized.append(edits)
        return SourceBroker(read, lambda value: {"paths": ["src/service.py"]}, authorize, writable=writable)

    def execute(self, worker, run_id="run-1", binding=None, writable=True):
        return worker.execute(binding or {"task": "one", "phase": "developer", "head": "exact"},
                              "Use broker then return JSON", SCHEMA, self.broker(writable), run_id)

    def state(self):
        return json.loads((self.root / "home" / "fixture-state.json").read_text())

    def test_one_turn_retrieves_and_revises_overlay_then_resumes_without_duplicate_usage(self):
        worker = self.worker()
        with patch.dict(os.environ, {"GH_TOKEN": "no", "OPENAI_API_KEY": "no", "SSH_AUTH_SOCK": "/not-mounted"}):
            first = self.execute(worker)
        self.assertEqual(first["result"]["edits"][0]["content"], "value = 3\n")
        self.assertEqual(first["result"]["edits"][0]["expected_sha256"], hashlib.sha256(b"value = 1\n").hexdigest())
        self.assertEqual(first["worker"]["tool_calls"], 4); self.assertFalse(first["worker"]["resumed"])
        self.assertEqual(self.execute(worker), first); self.assertEqual(self.state()["turns"], 1)
        second = self.execute(worker, "run-2")
        self.assertTrue(second["worker"]["resumed"]); self.assertEqual(second["usage"]["input_tokens"], 10)
        self.assertEqual(self.state()["threads"], 1); self.assertEqual(self.state()["turns"], 2)

    def test_cross_phase_and_changed_authority_use_separate_threads(self):
        worker = self.worker(); self.execute(worker)
        for index, binding in enumerate(({"task": "one", "phase": "reviewer", "head": "exact"},
                                         {"task": "one", "phase": "developer", "head": "new"})):
            value = self.execute(worker, "other-" + str(index), binding, writable=False)
            self.assertFalse(value["worker"]["resumed"]); self.assertEqual(value["result"]["edits"], [])
        self.assertEqual(self.state()["threads"], 3)

    def test_unknown_outcome_same_operation_never_relaunches_and_new_operation_starts_fresh(self):
        worker = self.worker("crash")
        with self.assertRaises(WorkerIndeterminate): self.execute(worker)
        with self.assertRaises(WorkerIndeterminate): self.execute(worker)
        self.assertEqual(self.state()["turns"], 1)
        healthy = self.worker()
        self.assertFalse(self.execute(healthy, "owner-retry-operation")["worker"]["resumed"])
        self.assertEqual(self.state()["turns"], 2)

    def test_replayed_request_cannot_change_input(self):
        worker = self.worker(); self.execute(worker)
        with self.assertRaisesRegex(WorkerError, "request changed"):
            worker.execute({"task": "one", "phase": "developer", "head": "exact"}, "changed", SCHEMA, self.broker(), "run-1")
        self.assertEqual(self.state()["turns"], 1)

    def test_malicious_protocol_or_builtin_tools_fail_closed(self):
        for scenario in ("forbidden-item", "forbidden-request", "wrong-thread", "changed-duplicate", "malformed"):
            with self.subTest(scenario=scenario):
                with self.assertRaises(WorkerIndeterminate): self.execute(self.worker(scenario), scenario)

    def test_bad_effective_config_stops_before_a_turn(self):
        with self.assertRaisesRegex(WorkerError, "effective capability"):
            self.execute(self.worker("bad-config"))
        self.assertFalse((self.root / "home" / "fixture-state.json").exists())

    def test_schema_pin_and_missing_smoke_stop_before_provider(self):
        worker = self.worker(); Path(self.profile["smoke_attestation"]).unlink()
        with self.assertRaisesRegex(WorkerError, "smoke is required"): worker.preflight()
        self.profile["schema_sha256"] = "0" * 64
        with self.assertRaisesRegex(WorkerError, "schema differs"): self.worker().preflight()
        self.assertFalse((self.root / "home" / "fixture-state.json").exists())

    def test_duplicate_tool_call_is_replayed_without_double_application(self):
        value = self.execute(self.worker("duplicate"))
        self.assertEqual(value["worker"]["tool_calls"], 4)
        self.assertEqual(len(self.authorized), 3)

    def test_tool_operation_and_byte_bounds(self):
        self.profile["max_tool_calls"] = 1
        with self.assertRaises(WorkerIndeterminate): self.execute(self.worker())
        self.assertEqual(self.authorized, [])

    def test_broker_rejects_traversal_scope_stale_hash_and_cumulative_patch(self):
        broker = self.broker()
        with self.assertRaises(WorkerError): broker.call("read_source", {"path": "../auth.json", "start_line": 1, "end_line": 2})
        with self.assertRaises(WorkerError): broker.call("command", {})
        for path, old in (("other.py", "absent"), ("src/service.py", "stale")):
            with self.assertRaises(WorkerError): broker.call("stage_edits", {"edits": [{"path": path, "expected_sha256": old, "delete": False, "content": "change"}]})
        self.assertEqual(broker.overlay, {})
        broker.max_patch_bytes = 1
        with self.assertRaises(WorkerError): broker.call("stage_edits", {"edits": [{"path": "src/service.py", "expected_sha256": hashlib.sha256(b"value = 1\n").hexdigest(), "delete": False, "content": "change"}]})
        self.assertEqual(broker.overlay, {})

    def test_completed_receipt_recovery_needs_no_preflight_or_process(self):
        worker = self.worker(); authority = {"task": "one", "phase": "developer", "head": "exact"}
        outer = {"request_hash": "outer", "role": "developer", "run_id": "run-1"}
        receipt = worker.execute(authority, "Use broker then return JSON", SCHEMA, self.broker(), "run-1", external_identity=outer)
        fresh = self.worker()
        with patch.object(fresh, "preflight", side_effect=AssertionError("No preflight on recovery")):
            self.assertEqual(fresh.recover_completed(authority, "Use broker then return JSON", SCHEMA, self.broker(), "run-1"), receipt)
            self.assertEqual(fresh.recover_bound(authority, "run-1", "", outer), receipt)
            with self.assertRaises(WorkerError): fresh.recover_bound(authority, "run-1", "", {**outer, "request_hash": "changed"})
        self.assertEqual(self.state()["turns"], 1)

    def test_commissioning_reuses_passed_turn_and_unknown_needs_explicit_retry(self):
        from agent_worker.smoke import run_smoke
        home = self.root / "home"
        first = run_smoke(self.profile, home, argv=self.argv)
        self.assertEqual(run_smoke(self.profile, home, argv=self.argv), first)
        self.assertEqual(self.state()["turns"], 1)
        Path(self.profile["smoke_attestation"]).unlink()
        # Completed inner receipt also restores a lost outer smoke attestation.
        self.assertEqual(run_smoke(self.profile, home, argv=self.argv)["operation"], first["operation"])
        self.assertEqual(self.state()["turns"], 1)
        with self.assertRaises(WorkerIndeterminate):
            run_smoke(self.profile, home, argv=self.argv + ["--scenario", "crash"], retry_smoke=True)
        # A prior successful attestation must not hide a newly authorized unknown turn.
        with self.assertRaises(WorkerIndeterminate): run_smoke(self.profile, home, argv=self.argv)
        self.assertEqual(self.state()["turns"], 2)
        recovered = run_smoke(self.profile, home, argv=self.argv, retry_smoke=True)
        self.assertNotEqual(recovered["operation"], first["operation"])
        self.assertEqual(self.state()["turns"], 3)

    def test_smoke_is_bound_to_model_and_adapter_and_keeps_other_model_attestations(self):
        from agent_worker.smoke import run_smoke
        home = self.root / "home"
        first = run_smoke(self.profile, home, argv=self.argv, model="one", adapter_identity="adapter-a")
        worker = AppServerWorker(self.profile, home, self.root / "workers", argv=self.argv, adapter_identity="adapter-a")
        worker.preflight(model="one")
        with self.assertRaisesRegex(WorkerError, "model/adapter"): worker.preflight(model="two")
        second = run_smoke(self.profile, home, argv=self.argv, model="two", adapter_identity="adapter-a")
        self.assertNotEqual(first["operation"], second["operation"])
        worker.preflight(model="one"); worker.preflight(model="two")
        worker.adapter_identity = "adapter-b"
        with self.assertRaisesRegex(WorkerError, "model/adapter"): worker.preflight(model="one")
        with self.assertRaisesRegex(WorkerError, "explicit --retry-smoke"):
            run_smoke(self.profile, home, argv=self.argv, model="one", adapter_identity="adapter-b")
        self.assertEqual(self.state()["turns"], 2)

    def test_cached_capability_check_never_reuses_smoke_for_another_model(self):
        worker = self.worker(); self.execute(worker)
        with self.assertRaisesRegex(WorkerError, "model/adapter"):
            worker.execute({"task": "one"}, "prompt", SCHEMA, self.broker(), "other-model", "different")
        self.assertEqual(self.state()["turns"], 1)

    def test_smoke_authority_hash_changes_with_the_authorizer_source(self):
        root = self.root / "adapter"; root.mkdir()
        (root / "authorize.py").write_text("old authority")
        before = source_identity(root, ["authorize.py"])
        (root / "authorize.py").write_text("changed authority")
        self.assertNotEqual(before, source_identity(root, ["authorize.py"]))

    def test_both_lock_entry_points_reject_symlinks_before_dispatch(self):
        from agent_worker.smoke import run_smoke
        worker = self.worker()
        target = self.root / "unrelated"; target.write_text("unchanged")
        binding = {"task": "one", "phase": "developer", "head": "exact"}
        session = worker.state_dir / fingerprint(worker.effect_identity(binding, ""))
        session.mkdir(parents=True); (session / "lock").symlink_to(target)
        with self.assertRaises(WorkerError): self.execute(worker)
        directory = Path(self.profile["smoke_attestation"] + ".worker")
        directory.mkdir(); (directory / "commissioning.lock").symlink_to(target)
        with self.assertRaises(WorkerError): run_smoke(self.profile, self.root / "home", argv=self.argv)
        self.assertEqual(target.read_text(), "unchanged")
        self.assertFalse((self.root / "home" / "fixture-state.json").exists())

    def test_correctable_tool_errors_are_bounded_and_fixed_within_one_turn(self):
        value = self.execute(self.worker("corrected-input"))
        self.assertEqual(value["worker"]["tool_calls"], 6)
        self.assertEqual(value["result"]["edits"][0]["content"], "value = 3\n")
        self.assertEqual(self.state()["turns"], 1)
        self.assertEqual(len(self.authorized), 3)

    def test_informational_startup_notices_can_arrive_before_or_after_config_response(self):
        for scenario in ("startup-notices", "startup-notices-after-config"):
            with self.subTest(scenario=scenario):
                value = self.execute(self.worker(scenario), scenario)
                self.assertEqual(value["result"]["edits"][0]["content"], "value = 3\n")
        self.assertEqual(self.state()["turns"], 2)

    def test_malformed_or_actionable_startup_notifications_fail_before_dispatch(self):
        for scenario in ("startup-bad-notice", "startup-bad-range", "startup-bad-timestamp", "startup-notice-action",
                         "startup-notice-request", "startup-forbidden", "startup-unknown"):
            with self.subTest(scenario=scenario):
                with self.assertRaises(WorkerError) as failure:
                    self.execute(self.worker(scenario), scenario)
                self.assertNotIn("never log notice parameters", str(failure.exception))
                self.assertNotIn("\n", str(failure.exception))
                if scenario == "startup-unknown":
                    self.assertIn("unknown/private?notice", str(failure.exception))
                self.assertFalse((self.root / "home" / "fixture-state.json").exists())


class WorkerBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_final_and_staged_edits_reject_the_same_malformed_proposals(self):
        original = "old"; sha = hashlib.sha256(original.encode()).hexdigest()
        valid = dict(path="source.py", expected_sha256=sha, delete=False, content="new")
        invalid = [None, {}, [valid, valid], [{**valid, "path": "../source.py"}],
            [{**valid, "expected_sha256": "stale"}], [{**valid, "delete": 1}],
            [{**valid, "content": "bad\0text"}], [{**valid, "content": original}],
            [{**valid, "delete": True}], [{**valid, "content": "x" * 101}],
            [{**valid, "extra": True}]]
        for edits in invalid:
            for mode in ("stage", "final"):
                with self.subTest(mode=mode, edits=edits):
                    called = []
                    broker = SourceBroker(lambda _: {"text": original, "sha256": sha}, lambda _: {},
                        called.append, writable=True, max_patch_bytes=100, max_changed_files=1)
                    with self.assertRaises(WorkerError):
                        if mode == "stage": broker.call("stage_edits", {"edits": edits})
                        else: broker.finalize({"verdict": "ready", "edits": edits})
                    self.assertEqual(called, []); self.assertEqual(broker.overlay, {})

    def test_lock_rejects_nonregular_hardlinked_and_symlink_parent(self):
        fifo = self.root / "fifo"; os.mkfifo(fifo)
        directory = self.root / "directory"; directory.mkdir()
        target = self.root / "file"; target.touch()
        hardlink = self.root / "hardlink"; os.link(target, hardlink)
        linked = self.root / "linked"; linked.symlink_to(directory, target_is_directory=True)
        for path in (fifo, directory, hardlink, linked / "lock"):
            with self.subTest(path=path), self.assertRaises(WorkerError), exclusive_lock(path): pass

    def test_lock_contention_is_enforced_by_the_os_and_released(self):
        import subprocess
        lock = self.root / "lock"
        code = "from pathlib import Path; from agent_worker.protocol import exclusive_lock;\nwith exclusive_lock(Path(__import__('sys').argv[1])): pass"
        with exclusive_lock(lock):
            child = subprocess.run([sys.executable, "-c", code, str(lock)], capture_output=True, timeout=5)
            self.assertNotEqual(child.returncode, 0)
        with exclusive_lock(lock): pass

    def connection(self, code, *, frame=1000, output=10000, timeout=1):
        from agent_worker.transport import _Connection
        return _Connection([sys.executable, "-c", code], self.root, dict(os.environ),
            dict(timeout_seconds=timeout, max_frame_bytes=frame, max_output_bytes=output))

    def test_real_split_frame_and_oversized_frame(self):
        connection = self.connection('import os,time; os.write(1,b\'{"value":\'); time.sleep(.05); os.write(1,b\'42}\\n\')')
        try: self.assertEqual(connection.message(), {"value": 42})
        finally: connection.close()
        self.assertIsNotNone(connection.process.poll())
        for code in ('import os; os.write(1,b"x"*2000)', 'import os; os.write(1,b"x"*2000+b"\\n")'):
            connection = self.connection(code)
            try:
                with self.assertRaisesRegex(WorkerError, "frame"): connection.message()
            finally: connection.close()
            self.assertIsNotNone(connection.process.poll())

    def test_aggregate_stderr_and_read_deadline(self):
        for code, error in [('import os; os.write(2,b"x"*11000)', 'aggregate'),
                            ('import sys; sys.stdin.read()', 'deadline')]:
            connection = self.connection(code)
            try:
                with self.assertRaisesRegex(WorkerError, error): connection.message()
            finally: connection.close()
            self.assertIsNotNone(connection.process.poll())

    def test_large_send_and_blocked_peer_has_a_deadline_and_is_reaped(self):
        connection = self.connection('import os; os.write(1,b"x"*1000000)', frame=200000)
        started = time.monotonic()
        try:
            with self.assertRaisesRegex(WorkerError, "deadline.*writing"):
                connection.send({"large": "x" * 100000})
        finally: connection.close()
        self.assertLess(time.monotonic() - started, 7)
        self.assertIsNotNone(connection.process.poll())

    def test_capability_output_is_stopped_before_the_child_can_continue(self):
        from agent_worker.capabilities import _run
        marker = self.root / "continued"
        code = 'import os,sys; from pathlib import Path; os.write(1,b"x"*1000000); Path(sys.argv[1]).touch()'
        with self.assertRaisesRegex(WorkerError, "output exceeded"):
            _run([sys.executable, "-c", code, str(marker)], cwd=self.root, env=dict(os.environ), limit=1024)
        self.assertFalse(marker.exists())
        with self.assertRaisesRegex(WorkerError, "timed out"):
            _run([sys.executable, "-c", 'import time; time.sleep(10)'], cwd=self.root,
                 env=dict(os.environ), timeout=.1)
