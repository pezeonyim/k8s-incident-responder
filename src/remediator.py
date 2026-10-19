"""Remediator: turns an approved ProposedAction into a real kubectl operation.

This module is fully deterministic. The LLM's job ended at diagnosis; from here
on, ordinary code decides what actually touches the cluster. Nothing the model
suggests reaches kubectl without passing through the sanity checks below.

Three allowlisted actions map onto two underlying operations:
  raise-memory-limit  -> kubectl patch (raise the container's memory ceiling)
  rollback-deployment -> kubectl rollout undo (revert to last known-good revision)
  patch-config        -> kubectl rollout undo (same revert; see note in build_command)
"""

import subprocess
import json
import re

# Kubernetes memory quantities we accept, e.g. "512Mi" or "1Gi".
# Anything that doesn't match this shape is rejected outright.
MEM_RE = re.compile(r"^(\d+)(Mi|Gi)$")


def build_command(action, workload, namespace) -> list[str]:
    """Map an action to the kubectl command that performs it.

    Returns the command as a list of args (never a shell string), so there is
    no shell interpolation and nothing to escape. This function only *builds*
    the command - it never executes anything.
    """
    if action.type == "raise-memory-limit":
        # The model's suggested limit is treated as untrusted input: it only
        # survives if safe_memory() accepts it, otherwise we substitute a default.
        new_limit = safe_memory(action.params.get("memory_limit"))
        patch = [{"op": "replace",
                  "path": "/spec/template/spec/containers/0/resources/limits/memory",
                  "value": new_limit}]
        return ["kubectl", "patch", "deployment", workload, "-n", namespace,
                "--type=json", "-p", json.dumps(patch)]

    # Both revert actions share one operation by design. We deliberately do NOT
    # let the system synthesize a corrected config and apply it to a live
    # cluster; for a bad-config failure the safe autonomous move is to revert to
    # the last revision known to work. Surgical config patching is a future
    # upgrade, gated behind stronger safeguards.
    elif action.type in ("rollback-deployment", "patch-config"):
        return ["kubectl", "rollout", "undo", f"deployment/{workload}", "-n", namespace]

    # Defense in depth: the Diagnosis schema already constrains action.type to
    # the allowlist, but we refuse anything unexpected here too rather than
    # falling through to some default behaviour.
    else:
        raise ValueError(f"unknown action type: {action.type}")


def safe_memory(value, default="512Mi"):
    """Validate a model-proposed memory limit, falling back to a safe default.

    Guards in both directions: an absurdly large value (a hallucinated "999Gi")
    would be rejected by the cluster or starve the node, while an absurdly small
    one would "fix" nothing and send the pod straight back into an OOM loop.
    Returning the default instead of raising keeps remediation working when the
    model returns junk.
    """
    m = MEM_RE.match(str(value))

    # Missing, malformed, or wrong-unit value (e.g. None, "lots", "5GB").
    if not m:
        return default

    amount = int(m.group(1))
    suffix = m.group(2)

    # Normalise to Mi so one comparison covers both units.
    if suffix == "Gi":
        amount *= 1024

    # Accepted window: 64Mi (too small to help below this) to 1Gi (hard cap).
    if amount < 64 or amount > 1024:
        return default

    return str(value)


def preview(command, workload, namespace):
    """Shows a preview of the command without making changes.

    Not every kubectl operation dry-runs the same way, so each branch previews
    in the way that operation allows.
    """
    if 'patch' in command:
        # The API server validates and reports the patch without persisting it.
        kub = command + ["--dry-run=server"]
        result = subprocess.run(kub, capture_output=True, text=True)
        # A rejected dry run reports on stderr, so fall back to it or we'd print nothing.
        print(result.stdout or result.stderr)

    elif 'undo' in command:
        # `rollout undo` has no server-side dry run, so the honest preview is to
        # state the intended command and show the revision history it would fall back to.
        print("would run:", " ".join(command))
        hist = ["kubectl", "rollout", "history", f"deployment/{workload}", "-n", namespace]
        result = subprocess.run(hist, capture_output=True, text=True)
        print(result.stdout or result.stderr)


def apply(command):
    """Execute the remediation.

    Returns the outcome rather than printing it, so the caller (the controller)
    can record it in the audit log and decide how to handle a failure.
    """
    result = subprocess.run(command, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


def check_policy(diagnosis, incident) -> tuple[bool, str]:
    """Return (allowed, reason)."""


def main():
    from diagnostician import ProposedAction
    a = ProposedAction(type="raise-memory-limit", params={"memory_limit": "512Mi"})
    cmd = build_command(a, "sample-app", "default")
    preview(cmd, "sample-app", "default")
    print(apply(cmd))


if __name__ == '__main__':
    main()
