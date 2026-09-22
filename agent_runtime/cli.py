"""Owner-operated governance runtime with resumable state and local review."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time

from .actions import action, upgrade
from .contracts import GOAL_SCHEMA, POLICY_SCHEMA, ROLE_SCHEMAS, validate_configuration
from .controller import Controller
from .github import GitHub
from .io import Closed, Unavailable, read_json
from .reasoning import Reasoning
from .store import Store
from .verification import Verification


def drive(engine, steps, poll):
    for _ in range(steps):
        value = engine.tick()
        print(json.dumps(value, ensure_ascii=False), flush=True)
        if value["status"] == "WAITING_EXTERNAL" and poll:
            time.sleep(poll)
        elif value["status"] != "RUNNING" or engine.state["paused"]:
            return 0 if value["status"] == "COMPLETED" else 2
    return 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("start", "doctor"):
        p = sub.add_parser(name)
        p.add_argument("--policy", type=Path, required=True)
        p.add_argument("--goal", type=Path, required=True)
        if name == "start":
            p.add_argument("--state", type=Path, required=True)
            p.add_argument("--trusted-local", action="store_true")
            p.add_argument("--max-steps", type=int, default=256)
            p.add_argument("--poll-seconds", type=int, default=0)
    p = sub.add_parser("resume")
    p.add_argument("--state", type=Path, required=True)
    p.add_argument("--max-steps", type=int, default=256)
    p.add_argument("--poll-seconds", type=int, default=0)
    p = sub.add_parser("serve")
    p.add_argument("--state", type=Path, required=True)
    p.add_argument("--poll-seconds", type=int, default=5)
    p.add_argument("--max-backoff", type=int, default=60)
    p = sub.add_parser("backup")
    p.add_argument("--state", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p = sub.add_parser("restore")
    p.add_argument("--state", type=Path, required=True)
    p.add_argument("--archive", type=Path, required=True)
    p = sub.add_parser("registry")
    p.add_argument("--root", type=Path, required=True,
                   help="One run, or a flat directory whose immediate children are runs")
    for name in ("status", "tick", "decision", "usage", "diagnostics", "review", "pause", "continue", "approve", "retry-effect", "reconcile-effect", "retry", "reconcile", "replan", "cancel", "upgrade"):
        p = sub.add_parser(name)
        p.add_argument("--state", type=Path, required=True)
        if name == "diagnostics":
            p.add_argument("--limit", type=int, default=20)
        if name in {"approve", "retry-effect", "reconcile-effect"}:
            p.add_argument("--binding", required=True)
        if name in {"pause", "continue", "approve", "retry-effect", "reconcile-effect", "retry", "reconcile", "replan", "cancel"}:
            p.add_argument("--reason", default="")
        if name == "upgrade":
            p.add_argument("--suspend", action="store_true")
        if name == "approve":
            p.add_argument("--decision-hash")
        if name == "review":
            p.add_argument("--port", type=int, default=8765)
            p.add_argument("--token-env", default="AGENT_REVIEW_TOKEN")
    p = sub.add_parser("schema")
    p.add_argument("name", choices=["policy", "goal", *ROLE_SCHEMAS])
    args = parser.parse_args(argv)
    try:
        if getattr(args, "max_steps", 1) < 1 or not 0 <= getattr(args, "poll_seconds", 0) <= 60:
            raise Closed("Step count must be positive and poll interval 0..60 seconds")
        if args.command == "schema":
            print(json.dumps({"policy": POLICY_SCHEMA, "goal": GOAL_SCHEMA, **ROLE_SCHEMAS}[args.name], indent=2))
        elif args.command == "doctor":
            policy, goal = read_json(args.policy), read_json(args.goal)
            from .doctor import diagnose
            result = diagnose(policy, goal)
            print(json.dumps(result))
            return 0 if result["ready"] else 2
        elif args.command == "start":
            engine = Controller.start(args.state, read_json(args.policy), read_json(args.goal), trusted_local=args.trusted_local)
            return drive(engine, args.max_steps, args.poll_seconds)
        elif args.command == "resume":
            return drive(Controller.resume(args.state), args.max_steps, args.poll_seconds)
        elif args.command == "serve":
            import signal
            import threading
            from .supervisor import supervise
            stop = threading.Event()
            previous = {sig: signal.signal(sig, lambda *_: stop.set()) for sig in (signal.SIGINT, signal.SIGTERM)}
            try:
                print(json.dumps(supervise(args.state, poll_seconds=args.poll_seconds,
                    max_backoff=args.max_backoff, stop=stop)))
            finally:
                for sig, handler in previous.items(): signal.signal(sig, handler)
        elif args.command in {"backup", "restore"}:
            from .backup import backup, restore
            print(json.dumps(backup(args.state, args.output) if args.command == "backup"
                             else restore(args.archive, args.state)))
        elif args.command == "registry":
            from .registry import registry_status
            print(json.dumps(registry_status(args.root), ensure_ascii=False))
        elif args.command in {"tick", "decision", "usage", "diagnostics"}:
            from .service import RunService
            method = getattr(RunService(args.state), args.command)
            print(json.dumps(method(args.limit) if args.command == "diagnostics" else method(), ensure_ascii=False))
        elif args.command == "review":
            from .review import create_server
            if not 1 <= args.port <= 65535:
                raise Closed("Review port must be 1..65535")
            with create_server(args.state, os.environ.get(args.token_env, ""), port=args.port) as server:
                print(f"Review: http://127.0.0.1:{server.server_port}", flush=True)
                try:
                    server.serve_forever()
                except KeyboardInterrupt:
                    pass
        elif args.command == "status":
            from .service import RunService
            print(json.dumps(RunService(args.state).status()))
        elif args.command == "upgrade":
            print(json.dumps(upgrade(args.state, suspend=args.suspend)))
        else:
            print(json.dumps(action(args.state, args.command, getattr(args, "binding", None),
                                    decision_hash=getattr(args, "decision_hash", None), reason=getattr(args, "reason", ""))))
        return 0
    except Exception as exc:
        from .diagnostics import error_response
        print(json.dumps(error_response(getattr(args, "state", None), exc, operation=args.command), ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
