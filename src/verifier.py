"""Verifier: confirms the app actually recovered after a remediation.

Deliberately reuses the watcher's own detection logic - "is it healthy?" is the
same question the watcher answers, so there is exactly one definition of health
in the system rather than two that can drift apart.
"""

import time

from watcher import get_pod_signals, evaluate


def verify(workload="sample-app", namespace="default", timeout=120, interval=5) -> tuple[bool, str]:
    """Poll until the workload is healthy or the timeout expires.

    Returns (recovered, detail). A timeout is a failure, not an exception - the
    controller needs to decide what to do about it (roll back), so it gets a
    value back rather than having to catch something.
    """
    deadline = time.time() + timeout
    last_symptom = None

    # Give the rollout a beat to start before the first check, so we don't read
    # the pre-change state and declare premature victory.
    time.sleep(interval)

    while time.time() < deadline:
        try:
            incident = evaluate(get_pod_signals(namespace=namespace, selector=f"app={workload}"),
                                workload=workload, namespace=namespace)
        except RuntimeError as e:
            return False, f"could not read cluster state: {e}"

        if incident is None:
            return True, "all pods ready"

        last_symptom = incident.symptom
        time.sleep(interval)

    return False, f"still unhealthy after {timeout}s (symptom: {last_symptom})"
