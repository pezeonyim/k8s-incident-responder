"""Append-only audit log.

Every observation, decision, and mutation the system makes is recorded here as
one JSON object per line. This is the accountability trail: if the system
touched the cluster, there is a line explaining what and why.

JSONL (one JSON object per line) rather than a single JSON array so that writes
are atomic appends - a crash mid-run can never corrupt earlier entries.
"""

import json
import os
from datetime import datetime, timezone

DEFAULT_LOG = os.getenv("AUDIT_LOG", "audit.jsonl")


def log_event(kind: str, data: dict, path: str = None) -> dict:
    """Append one event and return it (so callers can print/inspect it)."""
    event = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "kind": kind,
        **data,
    }
    target = path or DEFAULT_LOG
    parent = os.path.dirname(target)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(target, "a") as f:
        f.write(json.dumps(event, default=str) + "\n")
    return event


def read_events(path: str = None) -> list[dict]:
    """Read the log back. Bad lines are skipped rather than killing the reader."""
    target = path or DEFAULT_LOG
    events = []
    if not os.path.exists(target):
        return events
    with open(target) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events
