import subprocess
import json
from pydantic import BaseModel
import time

class PodSignal(BaseModel):
    """Represents the health and lifecycle state of a Kubernetes pod."""
    name: str
    ready: bool
    restart_count: int
    waiting_reason: str | None
    last_terminated_reason: str | None
    last_exit_code: int | None


class Incident(BaseModel):
    """Incident object given to the diagnostician."""
    workload: str
    namespace: str
    symptom: str
    pods: list[PodSignal]
    summary: str


def get_pod_signals(namespace="default", selector="app=sample-app") -> list[PodSignal]:
    """Gets pods from a Kubernetes namespace matching the given selector. Returns a list of PodSignals."""
    pod_signals = list()
    kub = f"kubectl get pods -n {namespace} -l {selector} -o json".split()
    result = subprocess.run(kub, capture_output=True, text=True)

    # Exit early if kubectl fails.
    if result.returncode != 0:
        raise RuntimeError(f"kubectl failed: {result.stderr.strip()}")
    
    pod = json.loads(result.stdout)

    for item in pod["items"]:
        cs = (item.get("status", {}).get("containerStatuses") or [{}])[0]
        term = cs.get("lastState", {}).get("terminated", {})
        curr_pod = PodSignal(
            name = item["metadata"]["name"],
            ready = cs.get("ready", False),
            restart_count = cs.get("restartCount", 0),
            waiting_reason = cs.get("state", {}).get("waiting", {}).get("reason"),
            last_terminated_reason = term.get("reason"),
            last_exit_code = term.get("exitCode"),
        )
        pod_signals.append(curr_pod)

    return pod_signals


def evaluate(pod_signals: list[PodSignal], workload="sample-app", namespace="default") -> Incident | None:
    """Takes a list of signals and evaluates if something went wrong."""
    # Return none (meaning no incidents) if all pods are ready.
    if all(p.ready for p in pod_signals):
        return None

    # Branch cases: Symptoms are ImagePullBackOff, OOMKilled, CrashLoopBackOff, or unhealthy.
    elif any(p.waiting_reason in ("ImagePullBackOff", "ErrImagePull") for p in pod_signals):
        symptom = "ImagePullBackOff"

    elif any(p.last_terminated_reason == "OOMKilled" or p.last_exit_code == 137 for p in pod_signals):
        symptom = "OOMKilled"

    elif any(p.waiting_reason == "CrashLoopBackOff" for p in pod_signals):
        symptom = "CrashLoopBackOff"

    else:
        symptom = "Unhealthy"

    # Number of pods that are not healthy.
    n = len([p for p in pod_signals if not p.ready])

    return Incident(
        workload = workload,
        namespace = namespace,
        symptom = symptom,
        pods = pod_signals,
        summary = f"{workload}: {symptom} ({n} of {len(pod_signals)} pods unhealthy)",
    )

def watch(interval=5):
    while True:
        incident = evaluate(get_pod_signals())
        if incident:
            print(incident.model_dump_json(indent=2))
        else:
            print("healthy — no incident")
        time.sleep(interval)

if __name__ == '__main__':
    watch()