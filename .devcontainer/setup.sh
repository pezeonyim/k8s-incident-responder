#!/usr/bin/env bash
# One-time setup for a Codespace / dev container: tools, Python env, nothing else.
# The cluster itself is NOT created here - that is the first thing you do by hand
# (or from the control panel), because watching it come up is part of the point.
set -euo pipefail

ARCH="$(dpkg --print-architecture)"          # amd64 | arm64

echo "==> kubectl"
if ! command -v kubectl >/dev/null 2>&1; then
  VER="$(curl -fsSL https://dl.k8s.io/release/stable.txt)"
  curl -fsSLo /tmp/kubectl "https://dl.k8s.io/release/${VER}/bin/linux/${ARCH}/kubectl"
  sudo install -m 0755 /tmp/kubectl /usr/local/bin/kubectl && rm -f /tmp/kubectl
fi
kubectl version --client

echo "==> kind"
if ! command -v kind >/dev/null 2>&1; then
  curl -fsSLo /tmp/kind "https://kind.sigs.k8s.io/dl/v0.30.0/kind-linux-${ARCH}"
  sudo install -m 0755 /tmp/kind /usr/local/bin/kind && rm -f /tmp/kind
fi
kind --version

echo "==> python environment"
python3 -m venv .venv
./.venv/bin/pip install --quiet --upgrade pip
./.venv/bin/pip install --quiet -r requirements.txt

[ -f .env ] || cp .env.example .env

cat <<'EOF'

────────────────────────────────────────────────────────────────────────
Ready. Two things before the responder can diagnose anything:

1. Bring up the cluster and the app:

     source .venv/bin/activate
     ./scripts/dev.sh cluster-up
     kubectl apply -f manifests/sample-app.yaml
     kubectl apply -f manifests/rbac.yaml

2. Choose a model. A Codespace has no GPU, so pick one:

   (a) Hosted API - fast, needs a key. Add it as a Codespaces secret, then
       in .env set LLM_PROVIDER=openai (or anthropic) and the matching
       *_MODEL to a current model id, and uncomment that client in
       requirements.txt before re-running pip install.

   (b) Local and free - slower on CPU. Install Ollama and pull a small model:

         curl -fsSL https://ollama.com/install.sh | sh
         ollama serve &
         ollama pull llama3.2:3b
         # then set OLLAMA_MODEL=llama3.2:3b in .env

Then:  python src/server.py     (port 8420 forwards automatically)
────────────────────────────────────────────────────────────────────────
EOF
