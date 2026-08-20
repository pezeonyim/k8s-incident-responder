#!/usr/bin/env bash
# Scenario 3/3: Failed rollout
# Rolls out a nonexistent image tag. The new pods can't pull the image
# (ErrImagePull -> ImagePullBackOff) and never become Ready, so the rollout
# stalls. Kubernetes keeps the OLD healthy pods serving traffic (rolling-update
# safety), so the app STAYS UP while the deploy is wedged.
# Undo with EITHER:  kubectl rollout undo deployment/sample-app   (the "rollback")
#                OR: ./scenarios/reset.sh                          (full restore)
set -euo pipefail
CTX="kind-incident-responder"
cd "$(dirname "$0")/.."

# Point the container at an image tag that does not exist.
kubectl --context "$CTX" set image deployment/sample-app web=nginx:99.99-does-not-exist

echo
echo "Bad image rolled out. Useful commands:"
echo "  kubectl get pods -l app=sample-app                 # old pods Running; new pods ImagePullBackOff"
echo "  kubectl rollout status deployment/sample-app       # 'Waiting for rollout...' = stuck (Ctrl-C to stop)"
echo "  kubectl get rs -l app=sample-app                   # old ReplicaSet READY, new ReplicaSet 0 ready"
echo "  kubectl describe pod -l app=sample-app | grep -iA4 events | tail   # ErrImagePull / ImagePullBackOff"
echo "  kubectl rollout undo deployment/sample-app         # <- the 'rollback-deployment' remediation"
echo "  ./scenarios/reset.sh                               # or full reset to healthy"
