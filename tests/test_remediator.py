"""Remediator: the model's parameters are untrusted, and actions map to one command."""

import json
from types import SimpleNamespace

import pytest

from remediator import build_command, safe_memory


def action(kind, **params):
    return SimpleNamespace(type=kind, params=params)


# --- safe_memory: the last line of defence before a number reaches the cluster ---

def test_accepts_a_sane_value():
    assert safe_memory("512Mi") == "512Mi"


def test_accepts_gi_and_converts_for_the_bound_check():
    # 1Gi == 1024Mi, exactly on the cap, so it is allowed.
    assert safe_memory("1Gi") == "1Gi"


def test_rejects_a_hallucinated_giant():
    # The specific failure this guard exists for: a model proposing "999Gi".
    assert safe_memory("999Gi") == "512Mi"


def test_rejects_a_uselessly_small_value():
    # Guards the other direction too - 8Mi would "fix" nothing and OOM again.
    assert safe_memory("8Mi") == "512Mi"


@pytest.mark.parametrize("junk", [None, "", "lots", "512", "5GB", "512 Mi", 512])
def test_rejects_malformed_values(junk):
    assert safe_memory(junk) == "512Mi"


def test_falls_back_to_the_caller_supplied_default():
    assert safe_memory("nonsense", default="256Mi") == "256Mi"


# --- build_command: three actions, two underlying operations ---

def test_raise_memory_limit_patches_the_deployment():
    cmd = build_command(action("raise-memory-limit", memory_limit="256Mi"),
                        "sample-app", "default")
    assert cmd[:4] == ["kubectl", "patch", "deployment", "sample-app"]
    patch = json.loads(cmd[cmd.index("-p") + 1])
    assert patch[0]["value"] == "256Mi"
    assert patch[0]["path"].endswith("/memory")


def test_a_bad_proposed_limit_never_reaches_the_command():
    cmd = build_command(action("raise-memory-limit", memory_limit="999Gi"),
                        "sample-app", "default")
    patch = json.loads(cmd[cmd.index("-p") + 1])
    assert patch[0]["value"] == "512Mi"


def test_rollback_and_patch_config_share_one_operation():
    # Deliberate design decision: a bad config is reverted, not rewritten.
    rollback = build_command(action("rollback-deployment"), "sample-app", "default")
    config = build_command(action("patch-config"), "sample-app", "default")
    assert rollback == config
    assert rollback[:3] == ["kubectl", "rollout", "undo"]


def test_rollback_ignores_model_supplied_params():
    # The model has been observed inventing a rollback target; `rollout undo`
    # needs none, so params must not leak into the command.
    cmd = build_command(action("rollback-deployment", new_version="nginx:latest"),
                        "sample-app", "default")
    assert "nginx:latest" not in cmd


def test_unknown_action_is_refused():
    # Defence in depth: the schema constrains this, and so does this function.
    with pytest.raises(ValueError):
        build_command(action("delete-namespace"), "sample-app", "default")


def test_commands_are_argument_lists_not_shell_strings():
    # No shell means nothing to escape or inject.
    cmd = build_command(action("rollback-deployment"), "sample-app", "default")
    assert isinstance(cmd, list) and all(isinstance(a, str) for a in cmd)
