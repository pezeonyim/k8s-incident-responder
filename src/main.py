"""Entry point.

  python src/main.py once        detect and, if something is broken, fix it
  python src/main.py watch       the same, continuously
  python src/main.py dashboard   build an HTML report from the audit log

Add --safe to require human approval before any change is applied.
"""

import argparse
import sys
import time

from watcher import get_pod_signals, evaluate
from controller import handle_incident


def detect(workload, namespace, wait=0, interval=3):
    """Look for an incident, optionally waiting up to `wait` seconds for one.

    The watcher deliberately ignores pods that are merely starting, so a failure
    injected a second ago has not produced any evidence yet. Waiting is the
    difference between "nothing is wrong" and "nothing is wrong *yet*".
    """
    deadline = time.time() + wait
    while True:
        signals = get_pod_signals(namespace=namespace, selector=f"app={workload}")
        incident = evaluate(signals, workload=workload, namespace=namespace)
        if incident is not None or time.time() >= deadline:
            return incident
        time.sleep(interval)


def run_once(workload, namespace, auto_approve, wait=0) -> dict | None:
    """One detect-and-handle pass. Returns the result record, or None if healthy."""
    incident = detect(workload, namespace, wait=wait)
    if incident is None:
        print("healthy - no incident"
              + (f" (waited {wait}s)" if wait else ""))
        return None

    detected_at = time.time()
    print(f"\n=== incident: {incident.summary} ===")
    result = handle_incident(incident, auto_approve=auto_approve, detected_at=detected_at)

    status = "RECOVERED" if result["recovered"] else "UNRESOLVED"
    mttr = f" in {result['mttr_seconds']}s" if result["mttr_seconds"] else ""
    print(f"\n=== {status}{mttr} | action: {result['action']} | {result['detail']} ===")
    return result


def run_watch(workload, namespace, auto_approve, interval, cooldown):
    """Watch continuously, handling each incident as it appears."""
    print(f"watching {workload} in {namespace} (every {interval}s) - Ctrl-C to stop")
    while True:
        try:
            result = run_once(workload, namespace, auto_approve)  # watch mode polls anyway
        except RuntimeError as e:
            print(f"cluster unreachable: {e}")
            result = None
        # After acting, pause longer so the cluster settles instead of
        # re-detecting the same incident mid-rollout.
        time.sleep(cooldown if result else interval)


def main():
    ap = argparse.ArgumentParser(description="Policy-constrained Kubernetes incident responder")
    ap.add_argument("mode", choices=["once", "watch", "dashboard"])
    ap.add_argument("--workload", default="sample-app")
    ap.add_argument("--namespace", default="default")
    ap.add_argument("--safe", action="store_true",
                    help="require human approval before applying any change")
    ap.add_argument("--interval", type=int, default=5, help="poll seconds (watch mode)")
    ap.add_argument("--wait", type=int, default=0,
                    help="seconds to wait for a failure to surface (once mode)")
    ap.add_argument("--cooldown", type=int, default=30, help="pause after acting (watch mode)")
    ap.add_argument("--out", default="dashboard.html", help="output path (dashboard mode)")
    args = ap.parse_args()

    if args.mode == "dashboard":
        from dashboard import build_dashboard
        path = build_dashboard(args.out)
        print(f"wrote {path}")
        return

    auto_approve = not args.safe
    if args.mode == "once":
        run_once(args.workload, args.namespace, auto_approve, wait=args.wait)
    else:
        try:
            run_watch(args.workload, args.namespace, auto_approve, args.interval, args.cooldown)
        except KeyboardInterrupt:
            print("\nstopped")
            sys.exit(0)


if __name__ == "__main__":
    main()
