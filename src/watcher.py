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


# Waiting reasons that mean "still starting", not "broken". A pod sitting in one
# of these is mid-rollout, which is normal and must not raise an incident.
STARTING_REASONS = {None, "ContainerCreating", "PodInitializing", "Pending"}


def _is_failing(p: PodSignal) -> bool:
    """True only when a pod shows actual evidence of failure.

    Being not-ready is NOT enough: every pod is briefly not-ready during a normal
    rollout. Requiring evidence stops the watcher firing on routine churn (which
    otherwise produces a stream of meaningless 'Unhealthy' incidents).
    """
    if p.ready:
        return False
    if p.waiting_reason not in STARTING_REASONS:
        return True          # CrashLoopBackOff, ImagePullBackOff, ErrImagePull, ...
    if p.last_terminated_reason or p.last_exit_code:
        return True          # it has died at least once
    return p.restart_count >= 1


def evaluate(pod_signals: list[PodSignal], workload="sample-app", namespace="default") -> Incident | None:
    """Takes a list of signals and evaluates if something went wrong."""
    # Classify from the failing pods only. Healthy bystanders - and pods left over
    # from an earlier incident - must not contribute evidence, or stale signals
    # (an old OOMKilled termination) hijack the verdict for an unrelated failure.
    failing = [p for p in pod_signals if _is_failing(p)]

    # No pod shows evidence of failure: either everything is ready, or something
    # is merely starting up. Neither is an incident.
    if not failing:
        return None

    # Branch cases: Symptoms are ImagePullBackOff, OOMKilled, CrashLoopBackOff, or unhealthy.
    # Order matters: a repeatedly OOMKilled pod ALSO reports CrashLoopBackOff, so
    # OOM must be tested first or every OOM is misread as a crash loop.
    if any(p.waiting_reason in ("ImagePullBackOff", "ErrImagePull") for p in failing):
        symptom = "ImagePullBackOff"

    elif any(p.last_terminated_reason == "OOMKilled" or p.last_exit_code == 137 for p in failing):
        symptom = "OOMKilled"

    # The literal CrashLoopBackOff waiting reason only appears once Kubernetes has
    # entered backoff. Before that there is a window where the container has
    # already died (lastState.terminated: Error / exit 1) but is still being
    # restarted - same failure, no label yet. Treat a non-OOM termination as the
    # crash-loop signature so a fast poll does not fall through to "Unhealthy".
    elif any(p.waiting_reason == "CrashLoopBackOff"
             or (p.last_terminated_reason and p.last_terminated_reason != "OOMKilled")
             for p in failing):
        symptom = "CrashLoopBackOff"

    else:
        symptom = "Unhealthy"

    # Number of pods that are not healthy.
    n = len(failing)

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