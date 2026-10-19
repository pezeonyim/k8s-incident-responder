"""Impersonation is applied only when RBAC is switched on."""

import importlib
import os


def reload_with(use_rbac: str):
    os.environ["USE_RBAC"] = use_rbac
    import identity
    importlib.reload(identity)
    import remediator
    importlib.reload(remediator)
    return identity, remediator


def test_no_impersonation_when_disabled():
    identity, remediator = reload_with("false")
    assert identity.as_remediator() == []
    cmd = remediator.build_command(
        type("A", (), {"type": "rollback-deployment", "params": {}})(), "sample-app", "default")
    assert "--as" not in cmd


def test_write_commands_impersonate_the_remediator_when_enabled():
    identity, remediator = reload_with("true")
    try:
        cmd = remediator.build_command(
            type("A", (), {"type": "rollback-deployment", "params": {}})(), "sample-app", "default")
        assert "--as" in cmd
        assert cmd[cmd.index("--as") + 1].endswith(":responder-remediator")
    finally:
        reload_with("false")       # leave the environment as the other tests expect
