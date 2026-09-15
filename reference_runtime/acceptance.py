"""Reference Git/probe observations for the portable typed acceptance contract."""
from control_plane_core.acceptance import acceptance_contract, evaluate_obligations
from control_plane_core import CoreError, require_merge_identity


def contract(selected):
    return acceptance_contract(selected["acceptance"], [
        {"criterion_id": a["id"], "kind": a.get("kind", "behavior"),
         "paths": a.get("paths", []), "targets": a.get("targets", [])} for a in selected["acceptance"]])


def evaluate(engine, selected, probes, stage):
    criteria = contract(selected)
    observed = {}
    by_probe = {r["probe_id"]: r for r in probes["probes"]}
    expected_sha = engine.state["merge_sha"] if stage == "postmerge" else engine.state["candidate_sha"]
    for row in criteria:
        if row["kind"] in {"behavior", "compatibility"}:
            observed[row["id"]] = probes["tested_sha"] == expected_sha and all(
                by_probe.get(p, {}).get("passed") is True for p in row["probe_ids"])
        elif row["kind"] == "documentation":
            # Git supplies exact revision bytes; computed review binds their existence.
            observed[row["id"]] = all(bool(engine.git("show", f"{expected_sha}:{path}", check=False).strip())
                                      for path in row["paths"])
        elif row["kind"] == "delivery" and stage == "postmerge":
            parents = engine.git("show", "-s", "--format=%P", expected_sha).split()
            try:
                require_merge_identity(engine.state["base_sha"], engine.state["candidate_sha"], parents)
                observed[row["id"]] = probes["all_passed"] and probes["tested_sha"] == expected_sha
            except CoreError:
                observed[row["id"]] = False
    return evaluate_obligations(criteria, observed, stage=stage)
