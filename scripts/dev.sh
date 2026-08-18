#!/usr/bin/env bash
# Dev helper for the k8s incident responder.
# Usage: ./scripts/dev.sh <command>
set -euo pipefail

CLUSTER_NAME="incident-responder"
KIND_CONFIG="manifests/kind-cluster.yaml"
VENV=".venv"

# Always run from the repo root (parent of this script's directory)
cd "$(dirname "$0")/.."

usage() {
  cat <<USAGE
Dev helper commands:
  check           Verify docker, kind, kubectl, python3 are installed & docker is running
  venv            Create the Python virtual environment (.venv)
  install         Install Python deps into the active .venv (activate it first)
  cluster-up      Create the local kind cluster
  cluster-down    Delete the local kind cluster
  cluster-status  Show cluster nodes and pods
USAGE
}

# Per-tool version probe (each CLI reports its version differently)
tool_version() {
  case "$1" in
    docker)  docker --version 2>/dev/null ;;
    kind)    kind --version 2>/dev/null ;;
    kubectl) kubectl version --client 2>/dev/null | head -1 ;;
    python3) python3 --version 2>/dev/null ;;
    *)       "$1" --version 2>/dev/null | head -1 ;;
  esac
}

cmd_check() {
  ok=1
  for tool in docker kind kubectl python3; do
    if command -v "$tool" >/dev/null 2>&1; then
      printf "  [ok]   %-8s %s\n" "$tool" "$(tool_version "$tool")"
    else
      printf "  [MISS] %-8s NOT FOUND\n" "$tool"; ok=0
    fi
  done
  if command -v docker >/dev/null 2>&1; then
    if docker info >/dev/null 2>&1; then echo "  [ok]   docker daemon is running"
    else echo "  [MISS] docker installed but daemon not running (start Docker Desktop)"; ok=0; fi
  fi
  if [ "$ok" = 1 ]; then echo "All prerequisites present."; else
    echo "Some prerequisites are missing - see the setup runbook."; return 1; fi
}

cmd_venv() {
  python3 -m venv "$VENV"
  echo "Created $VENV. Activate with:  source $VENV/bin/activate"
}

cmd_install() {
  if [ -z "${VIRTUAL_ENV:-}" ]; then
    echo "No active venv. Run:  source $VENV/bin/activate   then re-run: ./scripts/dev.sh install"; return 1
  fi
  pip install --upgrade pip
  pip install -r requirements.txt
}

cmd_cluster_up() {
  kind create cluster --name "$CLUSTER_NAME" --config "$KIND_CONFIG"
  kubectl cluster-info --context "kind-$CLUSTER_NAME"
}

cmd_cluster_down() { kind delete cluster --name "$CLUSTER_NAME"; }

cmd_cluster_status() {
  kubectl --context "kind-$CLUSTER_NAME" get nodes -o wide
  echo
  kubectl --context "kind-$CLUSTER_NAME" get pods -A
}

case "${1:-}" in
  check)          cmd_check ;;
  venv)           cmd_venv ;;
  install)        cmd_install ;;
  cluster-up)     cmd_cluster_up ;;
  cluster-down)   cmd_cluster_down ;;
  cluster-status) cmd_cluster_status ;;
  *)              usage ;;
esac
