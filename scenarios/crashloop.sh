#!/usr/bin/env bash
# Scenario 1/3: CrashLoopBackOff
# Mounts an intentionally broken nginx config onto sample-app so the container
# fails to start; Kubernetes then restarts it over and over (a "crash loop").
# Undo with:  ./scenarios/reset.sh
set -euo pipefail
CTX="kind-incident-responder"
cd "$(dirname "$0")/.."

# Applied (not patched) so ./scenarios/reset.sh can cleanly revert it.
kubectl --context "$CTX" apply -f - <<'YAML'
apiVersion: v1
kind: ConfigMap
metadata:
  name: sample-app-badconfig
  labels:
    app: sample-app
data:
  nginx.conf: |
    # 'bogus_directive' is not a real nginx directive -> nginx aborts on startup.
    bogus_directive;
    events {}
    http {
      server { listen 80; }
    }
---
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
      volumes:
        - name: badconfig
          configMap:
            name: sample-app-badconfig
      containers:
        - name: web
          image: nginx:1.27-alpine
          ports:
            - containerPort: 80
          volumeMounts:
            - name: badconfig
              mountPath: /etc/nginx/nginx.conf
              subPath: nginx.conf
          resources:
            requests: { cpu: "50m", memory: "32Mi" }
            limits:   { cpu: "250m", memory: "128Mi" }
          readinessProbe:
            httpGet: { path: /, port: 80 }
            initialDelaySeconds: 2
            periodSeconds: 5
          livenessProbe:
            httpGet: { path: /, port: 80 }
            initialDelaySeconds: 5
            periodSeconds: 10
YAML

echo
echo "Broken config injected. Useful commands:"
echo "  kubectl get pods -l app=sample-app -w                 # watch it crash-loop"
echo "  kubectl logs -l app=sample-app --tail=20              # see nginx's error"
echo "  kubectl describe pod -l app=sample-app | tail -25     # see the events"
echo "  ./scenarios/reset.sh                                  # restore health"
