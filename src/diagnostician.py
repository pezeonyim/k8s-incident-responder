import subprocess
import json
from pydantic import BaseModel, Field
from typing import Literal
from dotenv import load_dotenv
import os
import time
from identity import as_diagnostician

load_dotenv()
# Which backend performs the diagnosis. The rest of the system neither knows nor
# cares: it receives a validated Diagnosis either way.
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").strip().lower()
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")

# Default model per provider. Set these in .env - the hosted ids change over time,
# so check the provider's current docs rather than trusting a default.
_DEFAULT_MODEL = {
    "ollama": OLLAMA_MODEL,
    "openai": os.getenv("OPENAI_MODEL", ""),
    "anthropic": os.getenv("ANTHROPIC_MODEL", ""),
}

# Runtime override, set from the control panel. The default comes from .env.
_model_override: str | None = None


def set_model(name: str) -> None:
    global _model_override
    _model_override = name or None


def current_model() -> str:
    return _model_override or _DEFAULT_MODEL.get(LLM_PROVIDER) or OLLAMA_MODEL


def _call_model(prompt: str, model_name: str) -> str:
    """Send the prompt to the configured provider; return raw JSON text.

    Each provider is asked to emit JSON matching the Diagnosis schema. Ollama and
    OpenAI can constrain generation to the schema directly; Anthropic is given the
    schema in the prompt. In every case Pydantic validation (and the retry loop in
    diagnose) is what actually enforces the contract - the provider's own
    structured-output support is an optimisation, not the guarantee.
    """
    schema = Diagnosis.model_json_schema()

    if LLM_PROVIDER == "ollama":
        import ollama
        resp = ollama.chat(model=model_name,
                           messages=[{"role": "user", "content": prompt}],
                           format=schema)
        return resp["message"]["content"]

    if LLM_PROVIDER == "openai":
        from openai import OpenAI
        resp = OpenAI().chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_schema",
                             "json_schema": {"name": "diagnosis", "schema": schema}},
        )
        return resp.choices[0].message.content

    if LLM_PROVIDER == "anthropic":
        import anthropic
        resp = anthropic.Anthropic().messages.create(
            model=model_name, max_tokens=1500,
            messages=[{"role": "user", "content":
                       prompt + "\n\nRespond with ONLY a JSON object matching this schema, "
                                "no prose and no code fence:\n" + json.dumps(schema)}],
        )
        return resp.content[0].text

    raise ValueError(f"unknown LLM_PROVIDER '{LLM_PROVIDER}' "
                     f"(expected one of: ollama, openai, anthropic)")

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


def diagnose(incident, feedback=None, model=None):
    """Diagnose an incident. Returns the validated Diagnosis."""
    return diagnose_with_meta(incident, feedback=feedback, model=model)[0]


def diagnose_with_meta(incident, feedback=None, model=None):
    """As diagnose(), but also returns {model, seconds}.

    Which model produced a diagnosis, and how long it took, are properties of the
    *call* rather than of the diagnosis - so they are returned alongside rather
    than added to the schema. Putting them in the schema would ask the model to
    invent its own latency.
    """
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

    model_name = model or current_model()
    if not model_name:
        raise RuntimeError(f"no model configured for provider '{LLM_PROVIDER}' - "
                           f"set the matching *_MODEL variable in .env")
    started = time.time()
    raw = _call_model(prompt, model_name)
    diagnosis = Diagnosis.model_validate_json(raw)

    return diagnosis, {"model": model_name, "provider": LLM_PROVIDER,
                       "seconds": round(time.time() - started, 1)}

def main():
    from watcher import get_pod_signals, evaluate
    incident = evaluate(get_pod_signals())
    if incident is None:
        print("healthy — nothing to diagnose")
        return
    print(diagnose(incident).model_dump_json(indent=2))


if __name__ == "__main__":
    main()