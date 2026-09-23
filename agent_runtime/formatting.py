"""Human-readable projections; JSON remains the status/decision default."""
from .diagnostics import safe_text
from .explain import evidence_summary


def _text(value):
    if value is None:
        return "-"
    if type(value) is bool:
        return "yes" if value else "no"
    return safe_text(value, limit=4000).replace("\n", " ").replace("\r", " ").replace("\t", " ")


def table(rows):
    width = max((len(label) for label, _ in rows), default=0)
    return "\n".join(label.ljust(width) + "  " + _text(value) for label, value in rows)


def status_table(value):
    diagnostic, product = value.get("diagnostic") or {}, value.get("product") or {}
    rows = [("Run", value["run_id"]), ("Status", value["status"]), ("Paused", value["paused"]),
            ("Phase", value["phase"]), ("Item", value["item"]), ("Revision", value["revision"]),
            ("Model calls reserved", value["model_calls"]),
            ("Reason", diagnostic.get("message") or value.get("reason")), ("Error code", diagnostic.get("code")),
            ("Diagnostic ID", diagnostic.get("id")), ("Pending effect", value.get("pending_effect")),
            ("Candidate / observed head", value["head"]), ("Merge commit", value["merge_sha"]),
            ("Source checkout", product.get("source_checkout")), ("Run repository", product.get("repository")),
            ("Local base ref", product.get("base_ref")), ("Local base ref SHA", product.get("base_ref_sha"))]
    if product.get("inspection_error"):
        rows.append(("Repository inspection", product["inspection_error"]))
    return table(rows) + ("\n\n" + product["note"] if product else "")


def decision_table(value):
    diagnostic = value.get("diagnostic") or {}
    item = value.get("item") or {}
    rows = [("Run", value["run_id"]), ("Status", value["status"]), ("Paused", value["paused"]),
            ("Phase", value["phase"]), ("Item", item.get("id")), ("Attempt", value["attempt"]),
            ("Risk", value["risk"]), ("Base", value["base"]), ("Head", value["head"]),
            ("Reason", diagnostic.get("message") or value.get("reason")), ("Error code", diagnostic.get("code")),
            ("Diagnostic ID", diagnostic.get("id")), ("Approvable", value["approvable"]),
            ("Binding", value["binding"]), ("Decision hash", value["decision_hash"]),
            ("Pending effect", value["pending_effect"]),
            ("Owner actions", ", ".join(value["actions"]) or "none")]
    lines = [table(rows)]
    for role, review in value["reviews"].items():
        lines.append("\n" + role + ": " + _text(review.get("verdict")) + " — " + _text(review.get("summary")))
        for finding in review.get("findings", []):
            lines.append("  " + _text(finding.get("severity")) + ": " + _text(finding.get("description")))
    if value["evidence"]:
        lines.append("\nEvidence (complete details remain in --format json):")
        for name, proof in value["evidence"].items():
            lines.append("  " + name + ": " + evidence_summary(name, proof))
    lines.append("\nUse agent-control explain for conditions and exact recovery commands.")
    return "\n".join(lines)


def explain_text(value):
    status = value["status"]
    diagnostic = value["diagnostic"] or {}
    lines = [value["summary"], ""]
    if diagnostic:
        lines += [table([("Error code", diagnostic.get("code")), ("Failure phase", diagnostic.get("phase")),
                         ("Diagnostic ID", diagnostic.get("id"))]), ""]
    lines.append("Next step")
    action = value["next_action"]
    if action:
        lines += [action["description"], action["condition"], "  " + action["command"]]
    else:
        lines.append("No automatic recovery is recommended. Inspect the cause and the conditional actions below."
                     if status["status"] not in {"COMPLETED", "CANCELLED"} else "No recovery action is needed.")
    lines += ["  " + step for step in value["guidance"]]
    if diagnostic.get("details"):
        lines += ["", "Failure details", table([(str(k), v) for k, v in diagnostic["details"].items()])]
    for cause in diagnostic.get("exception", []):
        lines.append("Cause: " + _text(cause.get("type")) + " — " + _text(cause.get("message")))
        for frame in cause.get("frames", [])[-3:]:
            lines.append("  " + _text(frame.get("file")) + ":" + _text(frame.get("line")) + " in " + _text(frame.get("function")))
    lines += ["", "Run and result", status_table(status)]
    if value["pending_receipt"]:
        receipt = value["pending_receipt"]
        lines += ["", table([("Receipt", receipt["path"]), ("Present", receipt["present"])]), receipt["note"]]
    lines += ["", "Owner actions and conditions"]
    for row in value["actions"]:
        lines += [row["id"] + (" (conditional)" if row["enabled"] else " (unavailable)") + ": " + row["description"],
                  "  " + row["condition"], "  " + row["command"]]
    workflow = value["workflow"]
    if workflow["phases"]:
        lines += ["", "Workflow", table([("Risk", workflow["risk"]), ("Effective graph", workflow["level"]),
            ("Adaptive", workflow["adaptive"]), ("Critical", workflow["critical"]), ("Challenge", workflow["challenge"]),
            ("Resume phase", workflow["resume_phase"]), ("Risk-gate return", workflow["risk_gate_return"])])]
    lines += [workflow["note"], "", "Recent transitions", value["timeline_note"]]
    lines += ["  " + _text(row.get("phase")) + " -> " + _text(row.get("next")) + " | " + _text(row.get("status"))
              + (" | diagnostic " + _text(row["diagnostic_id"]) if row.get("diagnostic_id") else "")
              for row in value["timeline"]]
    lines += ["", "Recent diagnostic events"]
    lines += ["  " + _text(row.get("at")) + " | " + _text(row.get("code")) + " | " + _text(row.get("message"))
              + " | ID " + _text(row.get("id")) for row in value["diagnostics"]["events"]]
    lines += ["", table([("Reserved calls", value["usage"]["reserved_calls"]),
                         ("Recorded calls", value["usage"]["recorded_calls"]),
                         ("Unknown outcomes", value["usage"]["unknown_outcomes"])])]
    for warning in value["warnings"]:
        lines.append("Observation unavailable: " + warning)
    lines += ["", value["observation_note"]]
    return "\n".join(lines)
