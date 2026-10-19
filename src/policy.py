"""Policy gate: decides whether a proposed remediation is permitted.

This runs between the diagnostician (which only *suggests*) and the remediator
(which *acts*). It is deliberately redundant with the Diagnosis schema's
Literal constraint - defense in depth. If a Diagnosis ever reaches the
remediator by some other path (a test, a refactor, a future queue), this layer
still refuses anything it does not recognise.

It is a guard, not a decider: it blocks the indefensible and otherwise gets out
of the way. If policy fully dictated the action from the symptom, the
diagnostician's judgement would be pointless.
"""

import re

# The only actions this system is ever allowed to perform.
ALLOWED_ACTIONS = {"patch-config", "raise-memory-limit", "rollback-deployment"}

# Permissive coherence map: which actions are a defensible response to which
# symptom. More than one action per symptom on purpose - a crash loop could
# reasonably be fixed by correcting config OR reverting the bad deploy.
COHERENT_ACTIONS = {
    "OOMKilled": {"raise-memory-limit", "rollback-deployment"},
    "CrashLoopBackOff": {"patch-config", "rollback-deployment"},
    "ImagePullBackOff": {"rollback-deployment"},
    # Generic catch-all symptom: allow anything on the allowlist.
    "Unhealthy": set(ALLOWED_ACTIONS),
}

MEM_RE = re.compile(r"^(\d+)(Mi|Gi)$")


def check_policy(diagnosis, incident) -> tuple[bool, str]:
    """Return (allowed, reason).

    The reason is recorded in the audit log either way, so a refusal explains
    itself rather than silently dropping the incident.
    """
    action = diagnosis.proposed_action.type

    # Rule 1: allowlist. Independent re-check of what the schema constrains.
    if action not in ALLOWED_ACTIONS:
        return False, f"action '{action}' is not on the allowlist"

    # Rule 2: symptom/action coherence. Blocks the absurd - e.g. raising a
    # memory limit for an image-pull failure, which mutates the cluster to fix
    # a problem that has nothing to do with memory.
    coherent = COHERENT_ACTIONS.get(incident.symptom, set(ALLOWED_ACTIONS))
    if action not in coherent:
        return False, (
            f"action '{action}' is not a coherent response to symptom "
            f"'{incident.symptom}' (expected one of: {sorted(coherent)})"
        )

    # Rule 3: params sane for the action type. The remediator substitutes a safe
    # default for a bad memory value, so this is a note rather than a refusal -
    # we allow the fix to proceed, but the audit trail records that the model's
    # number was discarded.
    note = ""
    if action == "raise-memory-limit":
        proposed = diagnosis.proposed_action.params.get("memory_limit")
        if proposed is not None and not MEM_RE.match(str(proposed)):
            note = f" (note: proposed memory_limit '{proposed}' is malformed; a safe default will be used)"

    return True, f"action '{action}' permitted for symptom '{incident.symptom}'{note}"
