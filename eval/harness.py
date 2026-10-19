"""Evaluation harness: measures how reliably the system diagnoses and fixes.

An LLM-backed system is non-deterministic, so a single successful demo proves
very little. This runs each failure scenario N times and reports rates, not
anecdotes.

  python eval/harness.py --trials 10
  python eval/harness.py --trials 3 --scenarios oom crashloop

Each trial: reset to healthy -> inject a failure -> wait for detection ->
run the full controller pipeline -> record the outcome.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from watcher import get_pod_signals, evaluate          # noqa: E402
from controller import handle_incident                  # noqa: E402

# What a correct result looks like for each scenario. Several actions can be
# acceptable for one failure - a crash loop is legitimately fixable by either
# correcting config or reverting the bad deploy.
SCENARIOS = {
    "crashloop": {
        "script": "scenarios/crashloop.sh",
        "expected_symptom": "CrashLoopBackOff",
        "acceptable_actions": {"patch-config", "rollback-deployment"},
    },
    "oom": {
        "script": "scenarios/oom.sh",
        "expected_symptom": "OOMKilled",
        "acceptable_actions": {"raise-memory-limit"},
    },
    "rollout": {
        "script": "scenarios/rollout.sh",
        "expected_symptom": "ImagePullBackOff",
        "acceptable_actions": {"rollback-deployment"},
    },
}


def sh(script: str):
    return subprocess.run(["bash", os.path.join(ROOT, script)],
                          capture_output=True, text=True, cwd=ROOT)


def wait_for(predicate, timeout, interval=3):
    """Poll until predicate() returns a truthy value, or give up."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(interval)
    return None


def current_incident(workload, namespace):
    try:
        return evaluate(get_pod_signals(namespace=namespace, selector=f"app={workload}"),
                        workload=workload, namespace=namespace)
    except RuntimeError:
        return None


def run_trial(name, cfg, workload, namespace, audit_path) -> dict:
    """One full trial. Always leaves the cluster reset afterwards."""
    trial = {"scenario": name, "expected_symptom": cfg["expected_symptom"]}

    # Start from a known-good state so `rollout undo` has a healthy revision
    # to fall back to.
    sh("scenarios/reset.sh")
    if not wait_for(lambda: current_incident(workload, namespace) is None, timeout=90):
        trial.update(error="cluster did not return to healthy before trial")
        return trial

    sh(cfg["script"])

    # Detection: how long until the watcher sees it at all.
    t_inject = time.time()
    incident = wait_for(lambda: current_incident(workload, namespace), timeout=120)
    if incident is None:
        trial.update(error="failure never detected")
        sh("scenarios/reset.sh")
        return trial

    detected_at = time.time()
    trial["detect_seconds"] = round(detected_at - t_inject, 1)
    trial["detected_symptom"] = incident.symptom
    trial["symptom_correct"] = incident.symptom == cfg["expected_symptom"]

    result = handle_incident(incident, auto_approve=True,
                             detected_at=detected_at, audit_path=audit_path)

    trial.update({
        "action": result["action"],
        "action_correct": result["action"] in cfg["acceptable_actions"],
        "allowed": result["allowed"],
        "applied": result["applied"],
        "recovered": result["recovered"],
        "rolled_back": result["rolled_back"],
        "mttr_seconds": result["mttr_seconds"],
        "detail": result["detail"],
    })

    sh("scenarios/reset.sh")
    wait_for(lambda: current_incident(workload, namespace) is None, timeout=90)
    return trial


def summarise(trials: list[dict]) -> list[dict]:
    """Per-scenario rates. This is the table that goes in the README."""
    rows = []
    for name in SCENARIOS:
        group = [t for t in trials if t["scenario"] == name and "error" not in t]
        if not group:
            continue
        mttrs = sorted(t["mttr_seconds"] for t in group if t.get("mttr_seconds"))
        rows.append({
            "scenario": name,
            "trials": len(group),
            "symptom_accuracy": sum(t["symptom_correct"] for t in group) / len(group),
            "action_accuracy": sum(t["action_correct"] for t in group) / len(group),
            "remediation_success": sum(t["recovered"] for t in group) / len(group),
            "median_mttr": mttrs[len(mttrs) // 2] if mttrs else None,
            # Hard invariant: the policy layer should never let an action
            # outside the allowlist through, so this must stay at zero.
            "mutations_outside_allowlist": sum(1 for t in group if not t["allowed"] and t["applied"]),
        })
    return rows


def print_table(rows):
    hdr = f"{'scenario':<14}{'trials':>7}{'symptom':>10}{'action':>9}{'fixed':>8}{'MTTR':>7}{'escapes':>9}"
    print("\n" + hdr)
    print("-" * len(hdr))
    for r in rows:
        mttr = f"{r['median_mttr']:.0f}s" if r["median_mttr"] else "-"
        print(f"{r['scenario']:<14}{r['trials']:>7}"
              f"{r['symptom_accuracy']*100:>9.0f}%{r['action_accuracy']*100:>8.0f}%"
              f"{r['remediation_success']*100:>7.0f}%{mttr:>7}{r['mutations_outside_allowlist']:>9}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=5, help="trials per scenario")
    ap.add_argument("--scenarios", nargs="*", default=list(SCENARIOS), choices=list(SCENARIOS))
    ap.add_argument("--workload", default="sample-app")
    ap.add_argument("--namespace", default="default")
    args = ap.parse_args()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = os.path.join(ROOT, "eval", "runs")
    os.makedirs(run_dir, exist_ok=True)
    audit_path = os.path.join(run_dir, f"{stamp}-audit.jsonl")
    out_path = os.path.join(run_dir, f"{stamp}-results.json")

    trials = []
    total = args.trials * len(args.scenarios)
    i = 0
    for name in args.scenarios:
        for _ in range(args.trials):
            i += 1
            print(f"\n[{i}/{total}] {name}")
            t = run_trial(name, SCENARIOS[name], args.workload, args.namespace, audit_path)
            print("   ->", {k: t.get(k) for k in ("detected_symptom", "action", "recovered", "mttr_seconds")})
            trials.append(t)

    rows = summarise(trials)
    print_table(rows)
    with open(out_path, "w") as f:
        json.dump({"trials": trials, "summary": rows}, f, indent=2, default=str)
    print(f"\nresults: {out_path}\naudit:   {audit_path}")


if __name__ == "__main__":
    main()
