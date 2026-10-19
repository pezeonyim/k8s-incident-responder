"""Policy: a permissive guard that still refuses the indefensible."""

from types import SimpleNamespace

from policy import check_policy


def diagnosis(kind, **params):
    return SimpleNamespace(proposed_action=SimpleNamespace(type=kind, params=params))


def incident(symptom):
    return SimpleNamespace(symptom=symptom, workload="sample-app", namespace="default")


def test_permits_a_coherent_action():
    ok, reason = check_policy(diagnosis("raise-memory-limit", memory_limit="256Mi"),
                              incident("OOMKilled"))
    assert ok and "permitted" in reason


def test_refuses_an_action_outside_the_allowlist():
    ok, reason = check_policy(diagnosis("delete-namespace"), incident("OOMKilled"))
    assert not ok and "allowlist" in reason


def test_refuses_memory_fix_for_an_image_pull_failure():
    # REGRESSION: evaluation caught the model proposing this. Raising a memory
    # limit cannot fix a missing image, and mutates the cluster for no reason.
    ok, reason = check_policy(diagnosis("raise-memory-limit"), incident("ImagePullBackOff"))
    assert not ok and "coherent" in reason


def test_allows_more_than_one_sensible_action_per_symptom():
    # Policy guards, it does not decide - a crash loop is legitimately fixable
    # by correcting config OR reverting the bad deploy.
    for act in ("patch-config", "rollback-deployment"):
        ok, _ = check_policy(diagnosis(act), incident("CrashLoopBackOff"))
        assert ok, act


def test_generic_symptom_permits_any_allowlisted_action():
    for act in ("patch-config", "raise-memory-limit", "rollback-deployment"):
        ok, _ = check_policy(diagnosis(act), incident("Unhealthy"))
        assert ok, act


def test_malformed_params_are_noted_but_do_not_block_the_fix():
    # The remediator substitutes a safe default, so refusing here would leave a
    # fixable incident unfixed. The audit trail records that it was discarded.
    ok, reason = check_policy(diagnosis("raise-memory-limit", memory_limit="loads"),
                              incident("OOMKilled"))
    assert ok and "malformed" in reason
