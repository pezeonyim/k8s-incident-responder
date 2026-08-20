#!/usr/bin/env bash
# Scenario 2/3: OOMKilled
# Replaces nginx's normal startup with a process that grabs a FIXED ~300MB of
# memory, while the container's memory limit stays at 128Mi. The kernel kills it
# for exceeding the limit (exit code 137, Reason: OOMKilled), and it repeats.
# The footprint is fixed, so raising the limit above ~300Mi is what fixes it
# (that's the remediation your agent will propose later).
# Undo with:  ./scenarios/reset.sh
set -euo pipefail
CTX="kind-incident-responder"
cd "$(dirname "$0")/.."

kubectl --context "$CTX" apply -f - <<'YAML'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: sample-app
  labels:
    app: sample-app
spec:
  replicas: 2
  selector:
    matchLabels:
      app: sample-app
  template:
    metadata:
      labels:
        app: sample-app
    spec:
      containers:
        - name: web
          image: nginx:1.27-alpine
          # Deliberate memory hog: build a ~300MB string in memory (fixed size),
          # which exceeds the 128Mi limit below -> the kernel OOM-kills it.
          command: ["/bin/sh", "-c"]
          args:
            - |
              echo "allocating ~300MB (exceeds the limit on purpose)..."
              block=$(yes PADDING | head -c 300000000)
              echo "allocated, holding"
              sleep 3600
          resources:
            requests: { cpu: "50m", memory: "32Mi" }
            limits:   { cpu: "250m", memory: "128Mi" }   # too low on purpose
YAML

echo
echo "Memory hog injected. Useful commands:"
echo "  kubectl get pods -l app=sample-app -w                             # watch RESTARTS climb"
echo "  kubectl describe pod -l app=sample-app | grep -A4 'Last State'    # look for Reason: OOMKilled, Exit Code: 137"
echo "  kubectl logs -l app=sample-app --previous --tail=10              # note: little/no error - it was killed, not crashed"
echo "  ./scenarios/reset.sh                                             # restore health"
