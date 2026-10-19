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


def propose(incident, audit_path=None) -> dict:
    """Everything up to (but not including) the change: diagnose, policy-check,
    preview. Returns a proposal the caller can approve or reject.

    Split out from handle_incident so an operator-facing UI can hold the decision
    open. The gate is the same either way - this only changes who answers it.
    """
    out = {"incident": incident, "diagnosis": None, "allowed": False,
           "reason": "", "command": None, "preview": "", "error": None}

    log_event("incident_detected", {
        "workload": incident.workload, "symptom": incident.symptom,
        "summary": incident.summary,
        "unhealthy_pods": [p.name for p in incident.pods if not p.ready],
    }, audit_path)

    try:
        diagnosis = diagnose(incident)
    except Exception as e:
        out["error"] = f"diagnosis failed: {e}"
        log_event("diagnosis_failed", {"error": str(e)}, audit_path)
        return out

    def _log_diagnosis(d, retry=False):
        log_event("diagnosis", {
            "incident_type": d.incident_type, "root_cause": d.root_cause,
            "confidence": d.confidence, "action": d.proposed_action.type,
            "params": d.proposed_action.params, "evidence": d.evidence,
            "reasoning": d.reasoning, **({"retry": True} if retry else {}),
        }, audit_path)

    _log_diagnosis(diagnosis)
    allowed, reason = check_policy(diagnosis, incident)
    log_event("policy_decision", {"allowed": allowed, "reason": reason}, audit_path)

    # One corrected retry on refusal - the model gets another attempt, the rule does not move.
    if not allowed:
        log_event("rediagnosis_requested", {"reason": reason}, audit_path)
        try:
            diagnosis = diagnose(incident, feedback=reason)
        except Exception as e:
            out.update(diagnosis=diagnosis, reason=f"{reason}; re-diagnosis failed: {e}")
            return out
        _log_diagnosis(diagnosis, retry=True)
        allowed, reason = check_policy(diagnosis, incident)
        log_event("policy_decision", {"allowed": allowed, "reason": reason, "retry": True}, audit_path)

    out.update(diagnosis=diagnosis, allowed=allowed, reason=reason)
    if not allowed:
        return out

    command = build_command(diagnosis.proposed_action, incident.workload, incident.namespace)
    out["command"] = command
    log_event("remediation_proposed", {"command": command}, audit_path)
    out["preview"] = capture_preview(command, incident.workload, incident.namespace)
    return out


def capture_preview(command, workload, namespace) -> str:
    """preview() prints; the UI needs the text. Capture stdout without changing it."""
    import contextlib, io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        preview(command, workload, namespace)
    return buf.getvalue()


def execute(proposal, auto_approve=True, detected_at=None, audit_path=None,
            approval_reason=None) -> dict:
    """Apply an approved proposal, verify, and revert if it did not work."""
    incident = proposal["incident"]
    diagnosis = proposal["diagnosis"]
    command = proposal["command"]
    t0 = detected_at or time.time()
    workload, namespace = incident.workload, incident.namespace

    result = {
        "symptom": incident.symptom, "action": diagnosis.proposed_action.type,
        "allowed": True, "approved": True, "applied": False, "recovered": False,
        "rolled_back": False, "mttr_seconds": None, "detail": "",
    }
    log_event("approval", {"approved": True,
                           "reason": approval_reason or "auto-approved (demo mode)"}, audit_path)

    code, out, err = apply(command)
    result["applied"] = code == 0
    log_event("remediation_applied", {
        "command": command, "returncode": code,
        "stdout": out.strip(), "stderr": err.strip()}, audit_path)
    if code != 0:
        result["detail"] = f"apply failed: {err.strip()}"
        return result

    recovered, detail = verify(workload, namespace)
    result["recovered"], result["detail"] = recovered, detail
    log_event("verification", {"recovered": recovered, "detail": detail}, audit_path)

    if recovered:
        result["mttr_seconds"] = round(time.time() - t0, 1)
        log_event("incident_resolved", {"mttr_seconds": result["mttr_seconds"]}, audit_path)
        return result

    if diagnosis.proposed_action.type in REVERT_ACTIONS:
        log_event("unresolved", {"detail": "revert action did not restore health"}, audit_path)
        return result

    rollback = ProposedAction(type="rollback-deployment", params={})
    rb_command = build_command(rollback, workload, namespace)
    log_event("rollback_proposed", {
        "command": rb_command,
        "reason": "automatic revert of an unsuccessful remediation"}, audit_path)
    code, out, err = apply(rb_command)
    result["rolled_back"] = code == 0
    log_event("rollback_applied", {"returncode": code, "stdout": out.strip(),
                                   "stderr": err.strip()}, audit_path)
    recovered, detail = verify(workload, namespace)
    result["recovered"] = recovered
    result["detail"] = f"remediation failed; after rollback: {detail}"
    log_event("verification_after_rollback", {"recovered": recovered, "detail": detail}, audit_path)
    return result


def handle_incident(incident, auto_approve=True, detected_at=None, audit_path=None) -> dict:
    """Run one incident end to end: propose, gate, execute. Returns a result record.

    Composed from propose() + execute() so the unattended path and the operator
    -approved path in the control panel share exactly the same logic - there is no
    second implementation to drift out of sync.
    """
    t0 = detected_at or time.time()
    result = {"symptom": incident.symptom, "action": None, "allowed": False,
              "approved": False, "applied": False, "recovered": False,
              "rolled_back": False, "mttr_seconds": None, "detail": ""}

    p = propose(incident, audit_path=audit_path)
    if p.get("error"):
        result["detail"] = p["error"]
        return result

    result["action"] = p["diagnosis"].proposed_action.type
    result["allowed"] = p["allowed"]
    if not p["allowed"]:
        result["detail"] = p["reason"]
        return result

    print("\n--- preview ---")
    print(p["preview"], end="")

    approved, approval_reason = request_approval(p["diagnosis"], p["command"], auto_approve)
    result["approved"] = approved
    if not approved:
        log_event("approval", {"approved": False, "reason": approval_reason}, audit_path)
        result["detail"] = approval_reason
        return result

    outcome = execute(p, detected_at=t0, audit_path=audit_path,
                      approval_reason=approval_reason)
    result.update({k: outcome[k] for k in
                   ("applied", "recovered", "rolled_back", "mttr_seconds", "detail")})
    return result
