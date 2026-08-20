#!/usr/bin/env bash
# Restore sample-app to a healthy state (undo any injected scenario).
set -euo pipefail
CTX="kind-incident-responder"
cd "$(dirname "$0")/.."

# Re-applying the clean manifest removes any fields the injectors added
# (volumes, bad images, low limits) via kubectl's three-way merge.
kubectl --context "$CTX" apply -f manifests/sample-app.yaml
kubectl --context "$CTX" delete configmap sample-app-badconfig --ignore-not-found
echo
echo "Reset applied. Watch it return to healthy:"
echo "  kubectl get pods -l app=sample-app -w"
