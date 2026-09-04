import subprocess
import json
from pydantic import BaseModel, Field
from typing import Literal
import ollama
from dotenv import load_dotenv
import os
import re

MEM_RE = re.compile(r"^(\d+)(Mi|Gi)$")

def build_command(action, workload, namespace) -> list[str]:
    if action.type == "raise-memory-limit":
        new_limit = safe_memory(action.params.get("memory_limit"))
        patch = [{"op": "replace",
                  "path": "/spec/template/spec/containers/0/resources/limits/memory",
                  "value": new_limit}]
        return ["kubectl", "patch", "deployment", workload, "-n", namespace,
                "--type=json", "-p", json.dumps(patch)]
    elif action.type in ("rollback-deployment", "patch-config"):
        return ["kubectl", "rollout", "undo", f"deployment/{workload}", "-n", namespace]
    else:
        raise ValueError(f"unknown action type: {action.type}")


def safe_memory(value, default="512Mi"):
    m = MEM_RE.match(str(value))

    if not m:
        return default

    amount = int(m.group(1))
    suffix = m.group(2)

    if suffix == "Gi":
        amount *= 1024

    if amount < 64 or amount > 1024:
        return default

    return str(value)


def main():
    from diagnostician import ProposedAction
    for a in [
        ProposedAction(type="raise-memory-limit", params={"memory_limit": "256Mi"}),
        ProposedAction(type="raise-memory-limit", params={"memory_limit": "999Gi"}),  # cap should kick in
        ProposedAction(type="raise-memory-limit", params={}),                          # default should kick in
        ProposedAction(type="rollback-deployment", params={}),
        ProposedAction(type="patch-config", params={}),
    ]:
        print(a.type, "->", " ".join(build_command(a, "sample-app", "default")))


if __name__ == '__main__':
    main()