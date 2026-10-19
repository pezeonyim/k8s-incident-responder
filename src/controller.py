"""Controller: the sequential state machine that handles one incident.

The pipeline is deliberately linear - detect, diagnose, check, approve,
remediate, verify - because that is what the problem actually is. There is no
parallelism here to chase; concurrency only belongs inside evidence gathering.

Every step writes to the audit log, including refusals and failures, so the
record explains what the system did and why even when it chose to do nothing.
"""

import time

from audit import log_event
from diagnostician import diagnose, ProposedAction
from policy import check_policy
from remediator import build_command, preview, apply
from verifier import verify

# Actions that are themselves a revert; if one of these fails we do not "roll
# back the rollback", we just report.
REVERT_ACTIONS = {"rollback-deployment", "patch-config"}


def request_approval(diagnosis, command, auto_approve=True) -> tuple[bool, str]:
    """The approval gate.

    Auto-approves in demo mode. In safe mode it shows the human the exact
    command and waits for consent. Being able to flip this is the point: the
    system is equally capable of asking permission and of running unattended.
    """
    if auto_approve:
        return True, "auto-approved (demo mode)"

    print("\n--- approval required ---")
    print(f"diagnosis : {diagnosis.root_cause}")
    print(f"action    : {diagnosis.proposed_action.type}")
    print(f"command   : {' '.join(command)}")
    answer = input("apply this change? [y/N] ").strip().lower()
    if answer == "y":
        return True, "approved by operator"
    return False, "declined by operator"


def handle_incident(incident, auto_approve=True, detected_at=None, audit_path=None) -> dict:
    """Run one incident end to end. Returns a result record."""
    t0 = detected_at or time.time()
    workload, namespace = incident.workload, incident.namespace

    result = {
        "symptom": incident.symptom,
        "action": None,
        "allowed": False,
        "approved": False,
        "applied": False,
        "recovered": False,
        "rolled_back": False,
        "mttr_seconds": None,
        "detail": "",
    }

    log_event("incident_detected", {
        "workload": workload, "symptom": incident.symptom, "summary": incident.summary,
        "unhealthy_pods": [p.name for p in incident.pods if not p.ready],
    }, audit_path)

    # --- 1. diagnose (the only LLM step) ---
    try:
        diagnosis = diagnose(incident)
    except Exception as e:
        result["detail"] = f"diagnosis failed: {e}"
        log_event("diagnosis_failed", {"error": str(e)}, audit_path)
        return result

    result["action"] = diagnosis.proposed_action.type
    log_event("diagnosis", {
        "incident_type": diagnosis.incident_type,
        "root_cause": diagnosis.root_cause,
        "confidence": diagnosis.confidence,
        "action": diagnosis.proposed_action.type,
        "params": diagnosis.proposed_action.params,
        "evidence": diagnosis.evidence,
        "reasoning": diagnosis.reasoning,
    }, audit_path)

    # --- 2. policy check ---
    allowed, reason = check_policy(diagnosis, incident)
    result["allowed"] = allowed
    log_event("policy_decision", {"allowed": allowed, "reason": reason}, audit_path)
    if not allowed:
        result["detail"] = reason
        return result

    # --- 3. build + preview (nothing has changed yet) ---
    command = build_command(diagnosis.proposed_action, workload, namespace)
    log_event("remediation_proposed", {"command": command}, audit_path)
    print("\n--- preview ---")
    preview(command, workload, namespace)

    # --- 4. approval gate ---
    approved, approval_reason = request_approval(diagnosis, command, auto_approve)
    result["approved"] = approved
    log_event("approval", {"approved": approved, "reason": approval_reason}, audit_path)
    if not approved:
        result["detail"] = approval_reason
        return result

    # --- 5. apply ---
    code, out, err = apply(command)
    result["applied"] = code == 0
    log_event("remediation_applied", {
        "command": command, "returncode": code,
        "stdout": out.strip(), "stderr": err.strip(),
    }, audit_path)
    if code != 0:
        result["detail"] = f"apply failed: {err.strip()}"
        return result

    # --- 6. verify ---
    recovered, detail = verify(workload, namespace)
    result["recovered"] = recovered
    result["detail"] = detail
    log_event("verification", {"recovered": recovered, "detail": detail}, audit_path)

    if recovered:
        result["mttr_seconds"] = round(time.time() - t0, 1)
        log_event("incident_resolved", {"mttr_seconds": result["mttr_seconds"]}, audit_path)
        return result

    # --- 7. the fix did not work: revert it (unless it already was a revert) ---
    if diagnosis.proposed_action.type in REVERT_ACTIONS:
        log_event("unresolved", {"detail": "revert action did not restore health"}, audit_path)
        return result

    # Rollback is itself a consequential write, so it goes through the same
    # build -> approve -> apply -> verify path as any other change.
    rollback = ProposedAction(type="rollback-deployment", params={})
    rb_reason = "automatic revert of an unsuccessful remediation"
    rb_command = build_command(rollback, workload, namespace)
    rb_approved, rb_approval_reason = request_approval(diagnosis, rb_command, auto_approve)
    log_event("rollback_proposed", {
        "command": rb_command, "reason": rb_reason,
        "approved": rb_approved, "approval_reason": rb_approval_reason,
    }, audit_path)
    if not rb_approved:
        return result

    code, out, err = apply(rb_command)
    result["rolled_back"] = code == 0
    log_event("rollback_applied", {
        "returncode": code, "stdout": out.strip(), "stderr": err.strip(),
    }, audit_path)

    recovered, detail = verify(workload, namespace)
    result["recovered"] = recovered
    result["detail"] = f"remediation failed; after rollback: {detail}"
    log_event("verification_after_rollback", {"recovered": recovered, "detail": detail}, audit_path)
    return result
