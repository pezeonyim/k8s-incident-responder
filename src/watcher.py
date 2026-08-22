import subprocess
import json
from pydantic import BaseModel

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
    """Gets pods from a Kubernetes namespace matching the given selector."""
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

def main():
    for sig in get_pod_signals():
        print(sig)
        
if __name__ == '__main__':
    main()