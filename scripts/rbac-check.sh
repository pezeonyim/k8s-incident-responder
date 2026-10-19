#!/usr/bin/env bash
# Demonstrates that least privilege is enforced by the cluster.
#
#   1. the diagnostician identity can read pods          -> allowed
#   2. the diagnostician identity attempts a write       -> FORBIDDEN
#   3. the remediator identity attempts the same write   -> allowed
#
# Step 2 is the point: the read-only half of the system is incapable of changing
# the cluster, even if it tried.
set -u
cd "$(dirname "$0")/.."
NS=default
DIAG="system:serviceaccount:$NS:responder-diagnostician"
REMED="system:serviceaccount:$NS:responder-remediator"
PATCH='[{"op":"replace","path":"/spec/template/spec/containers/0/resources/limits/memory","value":"256Mi"}]'

echo "=== 1. diagnostician reads pods (expect: a pod list) ==="
kubectl --as="$DIAG" get pods -l app=sample-app -n $NS
echo
echo "=== 2. diagnostician attempts to patch (expect: Forbidden) ==="
if kubectl --as="$DIAG" patch deployment sample-app -n $NS --type=json -p "$PATCH" --dry-run=server 2>&1; then
  echo "!! UNEXPECTED: the read-only identity was allowed to write"
else
  echo "-> refused, as it should be"
fi
echo
echo "=== 3. remediator attempts the same patch (expect: allowed, dry run) ==="
kubectl --as="$REMED" patch deployment sample-app -n $NS --type=json -p "$PATCH" --dry-run=server
echo
echo "=== 4. remediator attempts to read logs (expect: Forbidden - not its job) ==="
POD=$(kubectl --as="$DIAG" get pods -l app=sample-app -n $NS -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
if [ -n "${POD:-}" ]; then
  if kubectl --as="$REMED" logs "$POD" -n $NS --tail=1 2>&1; then
    echo "!! UNEXPECTED: the write identity was allowed to read logs"
  else
    echo "-> refused, as it should be"
  fi
fi
