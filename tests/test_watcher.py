"""Watcher classification.

Most of these are regressions for bugs the evaluation harness caught: the first
eval run scored 100% remediation and 0% symptom accuracy, which exposed that the
watcher fired during normal rollout churn and mixed in signals from stale pods.
"""

from watcher import PodSignal, _is_failing, evaluate


def pod(name="p", ready=True, restarts=0, waiting=None, terminated=None, exit_code=None):
    return PodSignal(name=name, ready=ready, restart_count=restarts,
                     waiting_reason=waiting, last_terminated_reason=terminated,
                     last_exit_code=exit_code)


# --- _is_failing: evidence, not merely "not ready" ---

def test_a_ready_pod_is_not_failing():
    assert not _is_failing(pod(ready=True))


def test_a_starting_pod_is_not_failing():
    # REGRESSION: every pod is briefly not-ready during a normal rollout. Treating
    # that as an incident produced a stream of meaningless "Unhealthy" reports.
    assert not _is_failing(pod(ready=False, waiting="ContainerCreating"))
    assert not _is_failing(pod(ready=False, waiting=None))


def test_a_pod_with_a_bad_waiting_reason_is_failing():
    assert _is_failing(pod(ready=False, waiting="CrashLoopBackOff"))
    assert _is_failing(pod(ready=False, waiting="ImagePullBackOff"))


def test_a_pod_that_has_already_died_is_failing():
    assert _is_failing(pod(ready=False, terminated="Error", exit_code=1))


def test_a_restarting_pod_is_failing_even_without_a_reason():
    assert _is_failing(pod(ready=False, restarts=2))


# --- evaluate: when there is an incident, and what kind ---

def test_all_ready_is_no_incident():
    assert evaluate([pod(name="a"), pod(name="b")]) is None


def test_a_rollout_in_progress_is_no_incident():
    # REGRESSION: the harness polled seconds after injection and caught pods still
    # starting, which used to be reported as a generic "Unhealthy" incident.
    assert evaluate([pod(name="a"), pod(name="b", ready=False, waiting="ContainerCreating")]) is None


def test_no_pods_at_all_is_no_incident():
    assert evaluate([]) is None


def test_crash_loop_is_classified():
    inc = evaluate([pod(name="bad", ready=False, waiting="CrashLoopBackOff",
                        terminated="Error", exit_code=1)])
    assert inc.symptom == "CrashLoopBackOff"


def test_oom_wins_over_crash_loop():
    # A repeatedly OOMKilled pod ALSO reports CrashLoopBackOff. Checking crash
    # loop first would misclassify every OOM, so the ordering is load-bearing.
    inc = evaluate([pod(name="bad", ready=False, waiting="CrashLoopBackOff",
                        terminated="OOMKilled", exit_code=137)])
    assert inc.symptom == "OOMKilled"


def test_image_pull_wins_over_everything():
    inc = evaluate([pod(name="new", ready=False, waiting="ImagePullBackOff"),
                    pod(name="old", ready=False, terminated="OOMKilled", exit_code=137)])
    assert inc.symptom == "ImagePullBackOff"


def test_pre_backoff_crash_window_is_still_a_crash_loop():
    # REGRESSION: between the container dying and Kubernetes setting
    # waiting_reason=CrashLoopBackOff there is a window with only a terminated
    # state. A fast poll used to fall through to "Unhealthy" here.
    inc = evaluate([pod(name="bad", ready=False, waiting=None,
                        terminated="Error", exit_code=1)])
    assert inc.symptom == "CrashLoopBackOff"


def test_a_stale_bystander_does_not_hijack_classification():
    # REGRESSION: a crash loop was reported as OOMKilled because a leftover pod
    # from an earlier OOM scenario still carried last_terminated_reason=OOMKilled.
    # Healthy pods must contribute no evidence at all.
    stale_but_healthy = pod(name="old", ready=True, restarts=11,
                            terminated="OOMKilled", exit_code=137)
    crashing = pod(name="new", ready=False, waiting="CrashLoopBackOff",
                   terminated="Error", exit_code=1)
    inc = evaluate([stale_but_healthy, crashing])
    assert inc.symptom == "CrashLoopBackOff"


def test_incident_carries_every_pod_but_counts_only_failing_ones():
    # The diagnostician needs the bystanders for context (old vs new during a
    # failed rollout), while the summary should not overstate the damage.
    pods = [pod(name="a"), pod(name="b"),
            pod(name="c", ready=False, waiting="ImagePullBackOff")]
    inc = evaluate(pods)
    assert len(inc.pods) == 3
    assert "1 of 3" in inc.summary


def test_incident_records_workload_and_namespace():
    inc = evaluate([pod(ready=False, waiting="CrashLoopBackOff")],
                   workload="billing-api", namespace="prod")
    assert inc.workload == "billing-api" and inc.namespace == "prod"
