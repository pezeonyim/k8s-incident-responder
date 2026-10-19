import subprocess
import json
from pydantic import BaseModel, Field
from typing import Literal
import ollama
from dotenv import load_dotenv
import os
from identity import as_diagnostician

load_dotenv()
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")

class ProposedAction(BaseModel):
    """Class that constrains proposed action to three options."""
    type: Literal["patch-config", "raise-memory-limit", "rollback-deployment"]
    params: dict = {}


class Diagnosis(BaseModel):
    incident_type: str
    root_cause: str
    evidence: list[str]
    confidence: float = Field(ge=0, le=1)
    proposed_action: ProposedAction
    reasoning: str


def get_pod_logs(pod_name, namespace, previous=False):
    logs = f"kubectl logs {pod_name} -n {namespace} --tail=50".split() + as_diagnostician()

    if previous:
        logs.append("--previous")

    result = subprocess.run(logs, capture_output=True, text=True)

    return result.stdout


def get_pod_events(pod_name, namespace):
    events = f"kubectl describe pod {pod_name} -n {namespace}".split() + as_diagnostician()
    result = subprocess.run(events, capture_output=True, text=True)
    return result.stdout


def diagnose(incident, feedback=None):
    unhealthy = [p for p in incident.pods if not p.ready]
    evidence_text = ""
    for p in unhealthy:
        evidence_text += f"\n--- current logs [{p.name}] ---\n" + get_pod_logs(p.name, incident.namespace)
        evidence_text += f"\n--- previous logs [{p.name}] ---\n" + get_pod_logs(p.name, incident.namespace, previous=True)
        evidence_text += f"\n--- describe [{p.name}] ---\n" + get_pod_events(p.name, incident.namespace)

    prompt = f"""You are a Site Reliability Engineer diagnosing a failure in a Kubernetes deployment.

    An automated watcher flagged this incident:
    Workload:  {incident.workload}
    Namespace: {incident.namespace}
    Symptom:   {incident.symptom}
    Summary:   {incident.summary}

    Below is raw evidence from the unhealthy pods: container logs (current and previous
    instances) and `kubectl describe pod` output. Much of it is normal startup noise —
    find the line(s) that actually explain the failure and ignore the rest.

    === EVIDENCE ===
    {evidence_text}
    === END EVIDENCE ===

    Determine the root cause, then propose exactly ONE remediation. You may ONLY choose
    from these three actions:
    - "patch-config": the app was given a bad or missing configuration and needs it corrected.
    - "raise-memory-limit": the container was killed for exceeding its memory limit (OOMKilled) and needs a higher limit.
    - "rollback-deployment": a newly rolled-out version is broken (bad image or failing startup) and should be reverted to the previous version.

    Express confidence as a decimal between 0.0 and 1.0 (e.g. 0.9 for high confidence), not a percentage.

    The root_cause should describe the underlying problem, not the fix.

    Base your evidence strictly on what appears above; do not invent details. Set confidence honestly based on how clearly the evidence points to one cause."""

    # A refused proposal is re-diagnosed once with the refusal reason attached, so
    # the model can correct itself rather than the incident simply going unfixed.
    # The gate is never loosened - only the model gets another attempt.
    if feedback:
        prompt += (f"\n\nYour previous proposal was REJECTED by the safety policy:\n"
                   f"{feedback}\nPropose a different action that is valid for this symptom.")

    resp = ollama.chat(
        model=OLLAMA_MODEL,
        messages=[{"role": "user", "content": prompt}],
        format=Diagnosis.model_json_schema(),    # constrains output to the given schema
    )
    diagnosis = Diagnosis.model_validate_json(resp["message"]["content"])

    return diagnosis

def main():
    from watcher import get_pod_signals, evaluate
    incident = evaluate(get_pod_signals())
    if incident is None:
        print("healthy — nothing to diagnose")
        return
    print(diagnose(incident).model_dump_json(indent=2))


if __name__ == "__main__":
    main()