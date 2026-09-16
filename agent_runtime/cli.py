"""Owner-operated CLI; one controller process, resumable state, no dashboard."""
from __future__ import annotations

import argparse
import json
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
    for name in ("status", "pause", "continue", "approve", "retry-effect", "retry", "reconcile", "replan", "cancel", "upgrade"):
        p = sub.add_parser(name)
        p.add_argument("--state", type=Path, required=True)
        if name in {"approve", "retry-effect"}:
            p.add_argument("--binding", required=True)
        if name == "upgrade":
            p.add_argument("--suspend", action="store_true")
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
            validate_configuration(policy, goal)
            result = {"reasoning": Reasoning(policy["reasoning"]).preflight(),
                      "execution": Verification(policy["execution"]).preflight(), "model_called": False}
            if policy["publication"]["kind"] == "github":
                GitHub(policy["publication"], policy["base_branch"]).preflight()
                result["github_governance"] = "verified"
            print(json.dumps(result))
        elif args.command == "start":
            engine = Controller.start(args.state, read_json(args.policy), read_json(args.goal), trusted_local=args.trusted_local)
            return drive(engine, args.max_steps, args.poll_seconds)
        elif args.command == "resume":
            return drive(Controller(args.state), args.max_steps, args.poll_seconds)
        elif args.command == "status":
            state = Store(args.state).state
            task = state.get("task") or {}
            print(json.dumps({"status": state["status"], "phase": state["phase"], "paused": state["paused"],
                              "item": task.get("id"), "head": task.get("head"), "completed": state["completed"],
                              "reason": state.get("reason"), "approval": task.get("approval_required"),
                              "pending_effect": (state.get("pending") or {}).get("id")}))
        elif args.command == "upgrade":
            print(json.dumps(upgrade(args.state, suspend=args.suspend)))
        else:
            print(json.dumps(action(args.state, args.command, getattr(args, "binding", None))))
        return 0
    except (Closed, Unavailable, ValueError, OSError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
