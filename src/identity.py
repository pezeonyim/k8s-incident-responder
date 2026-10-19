"""Which Kubernetes identity each component acts as.

The responder runs outside the cluster, so it authenticates with the kubeconfig's
admin credentials. To make least privilege real rather than decorative, every
kubectl call is *impersonated* as one of two ServiceAccounts (`--as`). The API
server then authorises the request against that ServiceAccount's Role - so a
write attempted under the read-only identity is genuinely rejected by the
cluster, not merely avoided by our code.

Set USE_RBAC=false in .env to run without impersonation (e.g. before
`kubectl apply -f manifests/rbac.yaml` has been run).
"""

import os

NAMESPACE = os.getenv("K8S_NAMESPACE", "default")
USE_RBAC = os.getenv("USE_RBAC", "true").strip().lower() in ("1", "true", "yes")

DIAGNOSTICIAN = f"system:serviceaccount:{NAMESPACE}:responder-diagnostician"
REMEDIATOR = f"system:serviceaccount:{NAMESPACE}:responder-remediator"


def as_diagnostician() -> list[str]:
    """Read-only identity: pod state, logs, events."""
    return ["--as", DIAGNOSTICIAN] if USE_RBAC else []


def as_remediator() -> list[str]:
    """Write-scoped identity: patch and roll back deployments, nothing else.

    Used for the dry run too - a server-side dry run is still an authorised
    write request, so it fails under the read-only identity exactly as a real
    apply would.
    """
    return ["--as", REMEDIATOR] if USE_RBAC else []
